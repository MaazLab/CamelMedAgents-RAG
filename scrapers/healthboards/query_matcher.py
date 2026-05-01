from __future__ import annotations
import json
from collections import defaultdict

from scrapers.healthboards.config import SIMILARITY_THRESHOLD, TOP_K_MATCHES
from scrapers.healthboards.database import Database
from scrapers.healthboards.embedder import Embedder
from scrapers.healthboards.logger import get_logger
from scrapers.healthboards.vector_store import VectorStore

logger = get_logger("query_matcher")


def _parse_json_field(val: str | None):
    if val is None:
        return None
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return None
    return val


def _build_matched_query_entry(query: dict, similarity_score: float) -> dict:
    return {
        "query_id": query["id"],
        "original_text": query.get("original_text", ""),
        "label": query.get("label", ""),
        "category": query.get("category", ""),
        "symptoms": _parse_json_field(query.get("symptoms_json")),
        "duration": _parse_json_field(query.get("duration_json")),
        "frequency": query.get("frequency", ""),
        "triggers": _parse_json_field(query.get("triggers_json")),
        "symptom_temporal_map": _parse_json_field(query.get("symptom_temporal_map_json")),
        "patient_context": _parse_json_field(query.get("patient_context_json")),
        "clinical_interpretation": _parse_json_field(query.get("clinical_interpretation_json")),
        "representation_text": query.get("representation_text", ""),
        "similarity_score": round(similarity_score, 4),
    }


async def match_queries_to_posts(
    db: Database,
    vector_store: VectorStore,
    embedder: Embedder,
    source_id: int,
    similarity_threshold: float | None = None,
    top_k: int | None = None,
) -> None:
    """Match all queries to posts using semantic embedding similarity."""
    threshold = similarity_threshold if similarity_threshold is not None else SIMILARITY_THRESHOLD
    k = top_k or TOP_K_MATCHES

    labels = await db.get_all_query_labels(source_id)
    if not labels:
        logger.info("No queries found — skipping matching stage")
        return

    # Get IDs of queries that already have mappings so we can skip them
    pending_queries = await db.get_queries_pending_matching(source_id)
    pending_ids = {q["id"] for q in pending_queries}

    logger.info(
        "Starting semantic matching: %d labels, %d queries pending, threshold=%.2f, top_k=%d",
        len(labels), len(pending_ids), threshold, k,
    )

    total_mappings = 0
    total_queries = 0
    queries_with_matches = 0
    uncurated: list[str] = []

    point_query_map: dict[str, list[dict]] = defaultdict(list)

    for label in labels:
        queries = await db.get_queries_by_label(source_id, label)
        if not queries:
            continue

        logger.info("Label '%s': matching %d queries", label, len(queries))

        # Pre-build a cache of qdrant_point_id -> post.id for this label
        # to avoid repeated per-point DB lookups
        point_id_cache: dict[str, int | None] = {}

        for query in queries:
            total_queries += 1

            # Skip queries that already have mappings (resumability)
            if query["id"] not in pending_ids:
                queries_with_matches += 1
                continue

            representation = query.get("representation_text", "")
            if not representation:
                logger.debug("Query %d has no representation text, skipping", query["id"])
                uncurated.append(f"Q{query['id']}(no repr)")
                continue

            query_vector = embedder.encode_single(representation)

            results = vector_store.search_similar(
                query_vector=query_vector,
                disease_label=label,
                top_k=k,
                score_threshold=threshold,
            )

            if not results:
                uncurated.append(f"Q{query['id']}({label})")
                continue

            queries_with_matches += 1
            batch_mappings: list[tuple[int, int, float]] = []

            for scored_point in results:
                point_id = str(scored_point.id)

                # Use cache to avoid repeated DB lookups for the same point
                if point_id not in point_id_cache:
                    point_id_cache[point_id] = await db.get_post_db_id_by_qdrant_point(point_id)
                post_db_id = point_id_cache[point_id]

                if post_db_id is None:
                    continue

                batch_mappings.append((query["id"], post_db_id, scored_point.score))
                point_query_map[point_id].append(
                    _build_matched_query_entry(query, scored_point.score)
                )

            # Single commit for all mappings of this query
            inserted = await db.insert_query_post_mappings_batch(batch_mappings)
            total_mappings += inserted

        logger.info(
            "Label '%s': %d queries processed, %d total mappings so far",
            label, len(queries), total_mappings,
        )

    if point_query_map:
        logger.info("Updating matched_queries for %d Qdrant points", len(point_query_map))
        for point_id, query_entries in point_query_map.items():
            try:
                seen: set[int] = set()
                unique: list[dict] = []
                for entry in query_entries:
                    if entry["query_id"] not in seen:
                        seen.add(entry["query_id"])
                        unique.append(entry)
                vector_store.update_matched_queries(point_id, unique)
            except Exception as e:
                logger.debug("Failed to update payload for point %s: %s", point_id, e)

    queries_without = total_queries - queries_with_matches
    logger.info(
        "Matching complete: %d mappings, %d/%d queries curated, %d uncurated",
        total_mappings, queries_with_matches, total_queries, queries_without,
    )
    if uncurated and len(uncurated) <= 20:
        logger.info("Uncurated queries: %s", ", ".join(uncurated))
    elif uncurated:
        logger.info("Uncurated queries: %s ... and %d more", ", ".join(uncurated[:10]), len(uncurated) - 10)

    stats = await db.get_mapping_stats(source_id)
    logger.info(
        "Mapping stats: avg_score=%.4f, min=%.4f, max=%.4f, avg_posts/query=%.1f, avg_queries/post=%.1f",
        stats["avg_score"], stats["min_score"], stats["max_score"],
        stats["avg_posts_per_query"], stats["avg_queries_per_post"],
    )
