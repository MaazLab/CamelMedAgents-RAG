from __future__ import annotations
import json
from collections import defaultdict

from scrapers.patient_info.config import SIMILARITY_THRESHOLD, TOP_K_MATCHES, SOURCE_NAME
from scrapers.patient_info.database import Database
from scrapers.patient_info.embedder import Embedder
from scrapers.patient_info.logger import get_logger
from scrapers.patient_info.vector_store import VectorStore

logger = get_logger("query_matcher")


def _parse_json_field(val: str | None):
    """Deserialize a JSON string stored in SQLite, returning None on failure."""
    if val is None:
        return None
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return None
    return val


def _build_matched_query_entry(query: dict, similarity_score: float) -> dict:
    """Build a matched query payload entry with all query parameters."""
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

    logger.info(
        "Starting semantic matching: %d labels, threshold=%.2f, top_k=%d",
        len(labels), threshold, k,
    )

    total_mappings = 0
    total_queries = 0
    queries_with_matches = 0
    uncurated: list[str] = []

    # Track which queries map to each qdrant point so we can update payloads
    point_query_map: dict[str, list[dict]] = defaultdict(list)

    for label in labels:
        queries = await db.get_queries_by_label(source_id, label)
        if not queries:
            continue

        logger.info("Label '%s': matching %d queries", label, len(queries))

        for query in queries:
            total_queries += 1
            representation = query.get("representation_text", "")
            if not representation:
                logger.debug("Query %d has no representation text, skipping", query["id"])
                uncurated.append(f"Q{query['id']}(no repr)")
                continue

            # Embed the query representation
            query_vector = embedder.encode_single(representation)

            # Search Qdrant for similar posts within the same disease label
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
            label_mappings = 0

            for scored_point in results:
                # Resolve Qdrant point ID to post DB ID
                point_id = str(scored_point.id)
                post_db_id = await db.get_post_db_id_by_qdrant_point(point_id)
                if post_db_id is None:
                    logger.debug(
                        "Point %s not found in posts table, skipping",
                        point_id,
                    )
                    continue

                await db.insert_query_post_mapping(
                    query_id=query["id"],
                    post_id=post_db_id,
                    similarity_score=scored_point.score,
                )
                label_mappings += 1
                point_query_map[point_id].append(
                    _build_matched_query_entry(query, scored_point.score)
                )

            total_mappings += label_mappings

        logger.info(
            "Label '%s': %d queries processed, %d total mappings so far",
            label, len(queries), total_mappings,
        )

    # Update matched_queries in Qdrant payloads
    if point_query_map:
        logger.info("Updating matched_queries for %d Qdrant points", len(point_query_map))
        for point_id, query_entries in point_query_map.items():
            try:
                # Deduplicate by query_id
                seen: set[int] = set()
                unique: list[dict] = []
                for entry in query_entries:
                    if entry["query_id"] not in seen:
                        seen.add(entry["query_id"])
                        unique.append(entry)
                vector_store.update_matched_queries(point_id, unique)
            except Exception as e:
                logger.debug("Failed to update payload for point %s: %s", point_id, e)

    # Log summary
    queries_without = total_queries - queries_with_matches
    logger.info(
        "Matching complete: %d mappings, %d/%d queries curated, %d uncurated",
        total_mappings, queries_with_matches, total_queries, queries_without,
    )
    if uncurated and len(uncurated) <= 20:
        logger.info("Uncurated queries: %s", ", ".join(uncurated))
    elif uncurated:
        logger.info("Uncurated queries: %s ... and %d more", ", ".join(uncurated[:10]), len(uncurated) - 10)

    # Log detailed stats
    stats = await db.get_mapping_stats(source_id)
    logger.info(
        "Mapping stats: avg_score=%.4f, min=%.4f, max=%.4f, avg_posts/query=%.1f, avg_queries/post=%.1f",
        stats["avg_score"], stats["min_score"], stats["max_score"],
        stats["avg_posts_per_query"], stats["avg_queries_per_post"],
    )
