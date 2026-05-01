from __future__ import annotations
import asyncio
import hashlib
import json
import signal
import time

from scrapers.healthboards.board_mapper import BoardMapper
from scrapers.healthboards.config import (
    BASE_URL,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MODEL,
    JSONL_INPUT_PATH,
    SOURCE_NAME,
)
from scrapers.healthboards.database import Database
from scrapers.healthboards.embedder import Embedder
from scrapers.healthboards.healthboards_client import HealthBoardsClient, CloudflareBlockError
from scrapers.healthboards.logger import get_logger, setup_logging
from scrapers.healthboards.query_loader import load_queries
from scrapers.healthboards.query_matcher import match_queries_to_posts
from scrapers.healthboards.topic_discovery import TopicDiscovery
from scrapers.healthboards.vector_store import VectorStore, generate_point_id

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
        headless: bool = True,
        browser_timeout: int = 60_000,
    ) -> None:
        self.labels = labels
        self.max_topics_per_label = max_topics_per_label
        self.dry_run = dry_run
        self._qdrant_url = qdrant_url
        self._jsonl_path = jsonl_path or str(JSONL_INPUT_PATH)
        self._embedding_model = embedding_model or EMBEDDING_MODEL
        self._headless = headless
        self._browser_timeout = browser_timeout

        self._shutdown = False
        self._db: Database | None = None
        self._client: HealthBoardsClient | None = None
        self._source_id: int | None = None
        self._store: VectorStore | None = None
        self._embedder: Embedder | None = None

    async def run(self) -> None:
        setup_logging()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._handle_shutdown)

        db = Database()
        self._db = db
        await db.connect()

        async with HealthBoardsClient(
            headless=self._headless,
            browser_timeout=self._browser_timeout,
        ) as client:
            self._client = client
            try:
                self._source_id = await db.get_or_create_source(SOURCE_NAME, BASE_URL)

                # Stage 0: Load queries from JSONL (mandatory — pipeline stops on failure)
                await self._stage_load_queries()
                if self._shutdown:
                    return

                # Stage 1: Load board mappings
                mapper = await self._stage_load_mappings()

                # Derive labels from loaded queries; optionally narrow with --labels CLI flag
                query_labels = await db.get_all_query_labels(self._source_id)
                if self.labels:
                    labels = [l for l in query_labels if l in self.labels]
                else:
                    labels = query_labels
                logger.info(
                    "Pipeline running for %d labels (from queries): %s", len(labels), labels
                )

                discovery = TopicDiscovery(client, db, mapper, self._source_id)

                # Stage 2: Discover topics
                await self._stage_discover(discovery, labels)
                if self._shutdown:
                    return

                # Stage 3: Scrape thread content
                if not self.dry_run:
                    await self._stage_scrape(discovery, labels)
                    if self._shutdown:
                        return

                # Stage 4: Embed posts and upsert to Qdrant
                if not self.dry_run:
                    await self._stage_embed_and_upsert()
                    if self._shutdown:
                        return

                # Stage 5: Semantic matching — queries to posts
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
        t0 = time.time()
        try:
            await load_queries(self._db, self._source_id, self._jsonl_path)
        except (FileNotFoundError, ValueError) as exc:
            logger.error("Query loading failed — aborting pipeline: %s", exc)
            raise
        logger.info("Stage 0 complete (%.1fs)", time.time() - t0)

    # -- Stage 1: Load board mappings --

    async def _stage_load_mappings(self) -> BoardMapper:
        logger.info("=== Stage 1: Load Board Mappings ===")
        t0 = time.time()
        mapper = BoardMapper()
        mapper.load_mappings()
        logger.info("Stage 1 complete (%.1fs)", time.time() - t0)
        return mapper

    # -- Stage 2: Discover topics --

    async def _stage_discover(self, discovery: TopicDiscovery, labels: list[str]) -> None:
        logger.info("=== Stage 2: Topic Discovery ===")
        t0 = time.time()
        consecutive_cf_blocks = 0
        max_consecutive_cf_blocks = 3  # abort discovery if CF blocks N labels in a row
        for label in labels:
            if self._shutdown:
                logger.info("Shutdown: stopping discovery after label '%s'", label)
                return
            try:
                new_count = await discovery.discover_topics_for_label(
                    label, max_topics=self.max_topics_per_label
                )
                logger.info("Label '%s': discovered %d new topics", label, new_count)
                consecutive_cf_blocks = 0  # reset on success
            except CloudflareBlockError as e:
                consecutive_cf_blocks += 1
                logger.error(
                    "Discovery blocked by Cloudflare for label '%s' (%d/%d consecutive): %s",
                    label, consecutive_cf_blocks, max_consecutive_cf_blocks, e,
                    exc_info=True,
                )
                if consecutive_cf_blocks >= max_consecutive_cf_blocks:
                    logger.error(
                        "Aborting Stage 2: Cloudflare blocked %d consecutive labels. "
                        "Try running with --headless false, using a different network, "
                        "or waiting before retrying.",
                        max_consecutive_cf_blocks,
                    )
                    break
            except Exception as e:
                logger.error("Discovery failed for label '%s': %s", label, e, exc_info=True)
        logger.info("Stage 2 complete (%.1fs)", time.time() - t0)

    # -- Stage 3: Scrape thread content --

    async def _stage_scrape(self, discovery: TopicDiscovery, labels: list[str]) -> None:
        logger.info("=== Stage 3: Content Scraping ===")
        t0 = time.time()
        db = self._db
        consecutive_cf_blocks = 0
        max_consecutive_cf_blocks = 5  # higher tolerance for per-topic failures
        for label in labels:
            if self._shutdown:
                logger.info("Shutdown: stopping scraping after label '%s'", label)
                break
            pending = await db.get_pending_topics(
                self._source_id, disease_label=label
            )
            if not pending:
                continue
            logger.info("Label '%s': %d topics to scrape", label, len(pending))
            success, fail = 0, 0
            for topic_row in pending:
                if self._shutdown:
                    logger.info("Shutdown: stopping scraping mid-label '%s'", label)
                    break
                try:
                    ok = await discovery.scrape_topic(topic_row)
                    if ok:
                        success += 1
                        consecutive_cf_blocks = 0
                    else:
                        fail += 1
                except CloudflareBlockError as e:
                    consecutive_cf_blocks += 1
                    fail += 1
                    logger.error(
                        "Cloudflare blocked scraping topic %d (%d consecutive): %s",
                        topic_row["platform_topic_id"], consecutive_cf_blocks, e,
                        exc_info=True,
                    )
                    if consecutive_cf_blocks >= max_consecutive_cf_blocks:
                        logger.error(
                            "Aborting Stage 3: Cloudflare blocked %d consecutive topics.",
                            max_consecutive_cf_blocks,
                        )
                        break
                except Exception as e:
                    logger.error(
                        "Failed to scrape topic %d: %s",
                        topic_row["platform_topic_id"], e,
                        exc_info=True,
                    )
                    fail += 1
            logger.info("Label '%s': scraped %d, failed %d", label, success, fail)
            if consecutive_cf_blocks >= max_consecutive_cf_blocks:
                break
        logger.info("Stage 3 complete (%.1fs)", time.time() - t0)

    # -- Stage 4: Embed and Upsert to Qdrant --

    async def _stage_embed_and_upsert(self) -> None:
        logger.info("=== Stage 4: Embed & Qdrant Upsert ===")
        t0 = time.time()
        db = self._db
        embedder = Embedder(model_name=self._embedding_model)
        self._embedder = embedder

        store = VectorStore(qdrant_url=self._qdrant_url, embedding_dim=embedder.dimension)
        store.ensure_collection()
        self._store = store

        pending_posts = await db.get_posts_pending_upsert(self._source_id)
        reembed_posts = await db.get_posts_needing_reembed(self._source_id)

        all_posts = list(pending_posts or [])
        reembed_ids = {p["id"] for p in (reembed_posts or [])}
        for p in (reembed_posts or []):
            if p["id"] not in {pp["id"] for pp in all_posts}:
                all_posts.append(p)

        if not all_posts:
            logger.info("No posts pending embedding / upsert")
            logger.info("Stage 4 complete (%.1fs)", time.time() - t0)
            return

        logger.info(
            "%d posts to process (%d new, %d re-embed)",
            len(all_posts),
            len(all_posts) - len(reembed_ids & {p["id"] for p in all_posts}),
            len(reembed_ids),
        )

        # Build topic cache
        topic_cache: dict[int, dict] = {}
        for post in all_posts:
            topic_db_id = post["topic_id"]
            if topic_db_id not in topic_cache:
                topic_row = await db.get_topic_by_db_id(topic_db_id)
                if topic_row:
                    topic_cache[topic_db_id] = topic_row

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
            logger.info("Stage 4 complete (%.1fs)", time.time() - t0)
            return

        # Pre-compute thread context
        thread_post_map = await db.get_thread_context(self._source_id)
        thread_contexts = []
        for post, _topic in pairs:
            ptid = post["platform_topic_id"]
            sibling_ids = thread_post_map.get(ptid, [])
            thread_contexts.append({
                "thread_post_count": len(sibling_ids),
                "thread_point_ids": [
                    generate_point_id(BASE_URL, pid) for pid in sibling_ids
                ],
            })

        upsert_chunk_size = 2000
        total_upserted = 0

        for chunk_start in range(0, len(pairs), upsert_chunk_size):
            if self._shutdown:
                break
            chunk_end = min(chunk_start + upsert_chunk_size, len(pairs))
            chunk_pairs = pairs[chunk_start:chunk_end]
            chunk_contexts = thread_contexts[chunk_start:chunk_end]

            chunk_texts = [post["post_text"] for post, _ in chunk_pairs]
            logger.info(
                "Embedding chunk %d-%d (%d posts)...",
                chunk_start, chunk_end, len(chunk_texts),
            )
            chunk_vectors = embedder.encode(chunk_texts, batch_size=EMBEDDING_BATCH_SIZE)

            chunk_mqids = [[] for _ in chunk_pairs]
            point_ids = store.upsert_batch(
                chunk_pairs,
                embedding_vectors=chunk_vectors,
                source=BASE_URL,
                matched_queries_list=chunk_mqids,
                thread_contexts=chunk_contexts,
            )

            for (post, _), point_id in zip(chunk_pairs, point_ids):
                emb_hash = hashlib.sha256(
                    (post.get("post_text") or "").encode()
                ).hexdigest()[:16]
                await db.update_post_qdrant_id(post["id"], point_id, emb_hash)

            total_upserted += len(chunk_pairs)
            logger.info(
                "Upserted chunk %d-%d (%d/%d)",
                chunk_start, chunk_end, total_upserted, len(pairs),
            )

        logger.info("Upserted %d posts to Qdrant", total_upserted)
        logger.info("Stage 4 complete (%.1fs)", time.time() - t0)

    # -- Stage 5: Semantic matching --

    async def _stage_match(self) -> None:
        logger.info("=== Stage 5: Semantic Matching ===")
        t0 = time.time()
        await match_queries_to_posts(
            db=self._db,
            vector_store=self._store,
            embedder=self._embedder,
            source_id=self._source_id,
        )
        logger.info("Stage 5 complete (%.1fs)", time.time() - t0)
