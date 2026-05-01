from __future__ import annotations
import asyncio
import hashlib
import json
import signal

import numpy as np

from scrapers.patient_info.category_tag_mapper import CategoryTagMapper
from scrapers.patient_info.config import (
    DISCOURSE_BASE_URL,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    JSONL_INPUT_PATH,
    SOURCE_NAME,
)
from scrapers.patient_info.database import Database
from scrapers.patient_info.discourse_client import DiscourseClient
from scrapers.patient_info.embedder import Embedder
from scrapers.patient_info.logger import get_logger
from scrapers.patient_info.query_loader import load_queries
from scrapers.patient_info.query_matcher import match_queries_to_posts
from scrapers.patient_info.topic_discovery import TopicDiscovery
from scrapers.patient_info.vector_store import VectorStore, generate_point_id

logger = get_logger("pipeline")


class Pipeline:
    def __init__(
        self,
        labels: list[str] | None = None,
        max_topics_per_label: int | None = None,
        dry_run: bool = False,
        qdrant_url: str | None = None,
        jsonl_path: str | None = None,
        embedding_model: str | None = None,
    ) -> None:
        self.labels = labels
        self.max_topics_per_label = max_topics_per_label
        self.dry_run = dry_run
        self._qdrant_url = qdrant_url
        self._jsonl_path = jsonl_path or str(JSONL_INPUT_PATH)
        self._embedding_model = embedding_model or EMBEDDING_MODEL

        self._shutdown = False
        self._db: Database | None = None
        self._client: DiscourseClient | None = None
        self._source_id: int | None = None
        self._store: VectorStore | None = None
        self._embedder: Embedder | None = None

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._handle_shutdown)

        db = Database()
        self._db = db
        await db.connect()

        embedder = Embedder(model_name=self._embedding_model)
        self._embedder = embedder

        store = VectorStore(qdrant_url=self._qdrant_url, embedding_dim=embedder.dimension)
        store.ensure_collection()
        self._store = store

        async with DiscourseClient() as client:
            self._client = client
            try:
                self._source_id = await db.get_or_create_source(SOURCE_NAME, DISCOURSE_BASE_URL)

                # Stage 0: Load queries from JSONL (mandatory — pipeline stops on failure)
                await self._stage_load_queries()
                if self._shutdown:
                    return

                mapper = CategoryTagMapper()
                mapper.load_mappings()
                await mapper.fetch_and_cache(client)

                # Derive labels from loaded queries; optionally narrow with --labels CLI flag
                query_labels = await db.get_all_query_labels(self._source_id)
                if self.labels:
                    labels = [l for l in query_labels if l in self.labels]
                else:
                    labels = query_labels
                logger.info("Pipeline starting for %d labels (from queries): %s", len(labels), labels)

                discovery = TopicDiscovery(client, db, mapper, self._source_id)

                # Stage 1: Discover topics
                await self._stage_discover(discovery, labels)
                if self._shutdown:
                    return

                # Stage 2: Scrape topic content
                if not self.dry_run:
                    await self._stage_scrape(discovery, labels)
                    if self._shutdown:
                        return

                # Stage 3: Embed posts and upsert to Qdrant
                if not self.dry_run:
                    await self._stage_embed_and_upsert()
                    if self._shutdown:
                        return

                # Stage 4: Semantic matching — queries to posts
                if not self.dry_run:
                    await self._stage_match()

                # Print stats
                stats = await db.get_stats(self._source_id)
                logger.info("Pipeline complete. Stats: %s", json.dumps(stats, indent=2))

            finally:
                await db.close()
                logger.info("Pipeline shutdown complete")

    def _handle_shutdown(self) -> None:
        if self._shutdown:
            logger.warning("Forced shutdown — exiting immediately")
            raise SystemExit(1)
        logger.info("Graceful shutdown requested — finishing current operation...")
        self._shutdown = True

    # -- Stage 0: Load queries --

    async def _stage_load_queries(self) -> None:
        logger.info("=== Stage 0: Load Queries ===")
        try:
            await load_queries(self._db, self._source_id, self._jsonl_path)
        except (FileNotFoundError, ValueError) as exc:
            logger.error("Query loading failed — aborting pipeline: %s", exc)
            raise

    # -- Stage 1: Discover --

    async def _stage_discover(self, discovery: TopicDiscovery, labels: list[str]) -> None:
        logger.info("=== Stage 1: Topic Discovery ===")
        for label in labels:
            if self._shutdown:
                logger.info("Shutdown: stopping discovery after label '%s'", label)
                return
            try:
                new_count = await discovery.discover_topics_for_label(
                    label, max_topics=self.max_topics_per_label
                )
                logger.info("Label '%s': discovered %d new topics", label, new_count)
            except Exception as e:
                logger.error("Discovery failed for label '%s': %s", label, e)

    # -- Stage 2: Scrape --

    async def _stage_scrape(self, discovery: TopicDiscovery, labels: list[str]) -> None:
        logger.info("=== Stage 2: Content Scraping ===")
        db = self._db
        for label in labels:
            if self._shutdown:
                logger.info("Shutdown: stopping scraping after label '%s'", label)
                return

            pending = await db.get_pending_topics(self._source_id, disease_label=label)
            if not pending:
                continue

            logger.info("Label '%s': %d topics to scrape", label, len(pending))
            success, fail = 0, 0
            for topic_row in pending:
                if self._shutdown:
                    logger.info("Shutdown: stopping scraping mid-label '%s'", label)
                    return
                try:
                    ok = await discovery.scrape_topic(topic_row)
                    if ok:
                        success += 1
                    else:
                        fail += 1
                except Exception as e:
                    logger.error(
                        "Failed to scrape topic %d: %s",
                        topic_row["platform_topic_id"], e,
                    )
                    fail += 1

            logger.info("Label '%s': scraped %d, failed %d", label, success, fail)

    # -- Stage 3: Embed and Upsert to Qdrant --

    async def _stage_embed_and_upsert(self) -> None:
        logger.info("=== Stage 3: Embed & Qdrant Upsert ===")
        db = self._db
        store = self._store
        embedder = self._embedder

        # Get posts pending initial upsert
        pending_posts = await db.get_posts_pending_upsert(self._source_id)
        # Also get posts that need re-embedding (content changed)
        reembed_posts = await db.get_posts_needing_reembed(self._source_id)

        all_posts = list(pending_posts or [])
        reembed_ids = {p["id"] for p in (reembed_posts or [])}
        for p in (reembed_posts or []):
            if p["id"] not in {pp["id"] for pp in all_posts}:
                all_posts.append(p)

        if not all_posts:
            logger.info("No posts pending embedding / upsert")
            return

        logger.info(
            "%d posts to process (%d new, %d re-embed)",
            len(all_posts),
            len(all_posts) - len(reembed_ids & {p["id"] for p in all_posts}),
            len(reembed_ids),
        )

        # Build topic-id → topic-row mapping
        topic_cache: dict[int, dict] = {}
        for post in all_posts:
            topic_db_id = post["topic_id"]
            if topic_db_id not in topic_cache:
                topic_row = await db.get_topic_by_db_id(topic_db_id)
                if topic_row:
                    topic_cache[topic_db_id] = topic_row

        # Pair posts with topic rows
        pairs: list[tuple[dict, dict]] = []
        skipped = 0
        for post in all_posts:
            topic_row = topic_cache.get(post["topic_id"])
            if topic_row is None:
                skipped += 1
                continue
            pairs.append((post, topic_row))

        if skipped:
            logger.warning("Skipped %d posts — topic row not found", skipped)

        if not pairs:
            return

        # Pre-compute thread context: topic → all post IDs in that thread
        thread_post_map = await db.get_thread_context(self._source_id)
        thread_contexts = []
        for post, _topic in pairs:
            ptid = post["platform_topic_id"]
            sibling_ids = thread_post_map.get(ptid, [])
            thread_contexts.append({
                "thread_post_count": len(sibling_ids),
                "thread_point_ids": [
                    generate_point_id(DISCOURSE_BASE_URL, pid) for pid in sibling_ids
                ],
            })

        # Process in chunks to avoid OOM
        upsert_chunk_size = 2000
        total_upserted = 0

        for chunk_start in range(0, len(pairs), upsert_chunk_size):
            chunk_end = min(chunk_start + upsert_chunk_size, len(pairs))
            chunk_pairs = pairs[chunk_start:chunk_end]
            chunk_contexts = thread_contexts[chunk_start:chunk_end]

            # Embed this chunk only
            chunk_texts = [post["post_text"] for post, _ in chunk_pairs]
            logger.info("Embedding chunk %d-%d (%d posts)...", chunk_start, chunk_end, len(chunk_texts))
            chunk_vectors = embedder.encode(chunk_texts, batch_size=EMBEDDING_BATCH_SIZE)

            chunk_mqids = [[] for _ in chunk_pairs]
            point_ids = store.upsert_batch(
                chunk_pairs, embedding_vectors=chunk_vectors,
                matched_queries_list=chunk_mqids,
                thread_contexts=chunk_contexts,
            )

            # Record point IDs and text-based hashes back to SQLite per chunk
            for (post, _), point_id in zip(chunk_pairs, point_ids):
                emb_hash = hashlib.sha256((post.get("post_text") or "").encode()).hexdigest()[:16]
                await db.update_post_qdrant_id(post["id"], point_id, emb_hash)

            total_upserted += len(chunk_pairs)
            logger.info(
                "Upserted chunk %d-%d (%d/%d)",
                chunk_start, chunk_end, total_upserted, len(pairs),
            )

        logger.info("Upserted %d posts to Qdrant", total_upserted)

    # -- Stage 4: Semantic Matching --

    async def _stage_match(self) -> None:
        logger.info("=== Stage 4: Semantic Matching ===")
        await match_queries_to_posts(
            db=self._db,
            vector_store=self._store,
            embedder=self._embedder,
            source_id=self._source_id,
        )
