#!/usr/bin/env python3
"""Verification tool: coverage report, duplicate detection, and query mapping stats."""
from __future__ import annotations
import argparse
import asyncio

from scrapers.patient_info.config import DISCOURSE_BASE_URL, EMBEDDING_DIM, SOURCE_NAME
from scrapers.patient_info.database import Database
from scrapers.patient_info.logger import setup_logging, get_logger
from scrapers.patient_info.vector_store import VectorStore

logger = get_logger("verify")


async def run_verification(qdrant_url: str | None = None) -> None:
    db = Database()
    await db.connect()
    source_id = await db.get_or_create_source(SOURCE_NAME, DISCOURSE_BASE_URL)

    print("\n" + "=" * 60)
    print("  SCRAPER VERIFICATION REPORT")
    print("=" * 60)

    # -- Coverage per disease label --
    print("\n--- Coverage by Disease Label ---")
    cursor = await db.db.execute(
        """SELECT disease_label,
                  COUNT(*) as topic_count,
                  SUM(CASE WHEN scrape_status='scraped' THEN 1 ELSE 0 END) as scraped,
                  SUM(CASE WHEN scrape_status='failed' THEN 1 ELSE 0 END) as failed,
                  SUM(CASE WHEN scrape_status='discovered' THEN 1 ELSE 0 END) as pending
           FROM topics WHERE source_id = ?
           GROUP BY disease_label ORDER BY disease_label""",
        (source_id,),
    )
    rows = await cursor.fetchall()
    print(f"  {'Label':<30} {'Topics':>7} {'Scraped':>8} {'Failed':>7} {'Pending':>8}")
    print(f"  {'-'*30} {'-'*7} {'-'*8} {'-'*7} {'-'*8}")
    for r in rows:
        print(f"  {r[0] or 'unknown':<30} {r[1]:>7} {r[2]:>8} {r[3]:>7} {r[4]:>8}")

    # -- Posts per label --
    print("\n--- Posts by Disease Label ---")
    cursor = await db.db.execute(
        """SELECT t.disease_label,
                  COUNT(p.id) as post_count
           FROM posts p
           JOIN topics t ON p.topic_id = t.id
           WHERE p.source_id = ?
           GROUP BY t.disease_label ORDER BY t.disease_label""",
        (source_id,),
    )
    rows = await cursor.fetchall()
    print(f"  {'Label':<30} {'Posts':>7}")
    print(f"  {'-'*30} {'-'*7}")
    for r in rows:
        print(f"  {r[0] or 'unknown':<30} {r[1]:>7}")

    # -- Summary stats --
    stats = await db.get_stats(source_id)
    print(f"\n--- Summary ---")
    print(f"  Topics: {stats['topics']}")
    print(f"  Total posts: {stats['total_posts']}")
    print(f"  Upserted to Qdrant (SQLite): {stats['upserted_to_qdrant']}")

    # -- Qdrant document store --
    print("\n--- Qdrant Document Store ---")
    try:
        store = VectorStore(qdrant_url=qdrant_url, embedding_dim=EMBEDDING_DIM)
        store.ensure_collection()
        qdrant_count = store.count(source=SOURCE_NAME)
        sqlite_upserted = stats["upserted_to_qdrant"]
        print(f"  Points in Qdrant (source='{SOURCE_NAME}'): {qdrant_count}")
        if qdrant_count == sqlite_upserted:
            print(f"  OK — Qdrant count matches SQLite upserted count ({sqlite_upserted})")
        else:
            print(
                f"  MISMATCH — Qdrant={qdrant_count}, SQLite upserted={sqlite_upserted}. "
                "Re-run the pipeline to sync."
            )

        # Embedding dimension check
        info = store.get_collection_info()
        actual_dim = info.config.params.vectors.size
        print(f"  Collection embedding dimension: {actual_dim}")
        if actual_dim == EMBEDDING_DIM:
            print(f"  OK — matches configured EMBEDDING_DIM ({EMBEDDING_DIM})")
        else:
            print(
                f"  MISMATCH — collection dim={actual_dim}, config EMBEDDING_DIM={EMBEDDING_DIM}. "
                "You may need to recreate the collection."
            )
    except Exception as e:
        print(f"  Could not connect to Qdrant: {e}")

    # -- Query Mapping Stats --
    print("\n--- Query Mapping Stats ---")
    try:
        mapping_stats = await db.get_mapping_stats(source_id)
        print(f"  Total queries loaded: {mapping_stats['total_queries']}")
        print(f"  Queries with matches: {mapping_stats['queries_with_matches']}")
        print(f"  Queries without matches: {mapping_stats['queries_without_matches']}")
        print(f"  Total mappings: {mapping_stats['total_mappings']}")
        if mapping_stats['total_mappings'] > 0:
            print(f"  Similarity scores — avg: {mapping_stats['avg_score']:.4f}, "
                  f"min: {mapping_stats['min_score']:.4f}, max: {mapping_stats['max_score']:.4f}")
            print(f"  Avg posts per query: {mapping_stats['avg_posts_per_query']:.1f}")
            print(f"  Avg queries per post: {mapping_stats['avg_queries_per_post']:.1f}")
        else:
            print("  No mappings yet — run the full pipeline to generate semantic matches.")
    except Exception as e:
        print(f"  Could not retrieve mapping stats: {e}")

    # -- Duplicate detection --
    print("\n--- Duplicate Detection ---")
    cursor = await db.db.execute(
        """SELECT platform_topic_id, COUNT(*) as cnt
           FROM topics WHERE source_id = ?
           GROUP BY platform_topic_id HAVING cnt > 1""",
        (source_id,),
    )
    dupes = await cursor.fetchall()
    if dupes:
        print(f"  Found {len(dupes)} duplicate topic IDs:")
        for d in dupes[:10]:
            print(f"    topic_id={d[0]}, count={d[1]}")
    else:
        print("  No duplicate topics found")

    cursor = await db.db.execute(
        """SELECT platform_post_id, COUNT(*) as cnt
           FROM posts WHERE source_id = ?
           GROUP BY platform_post_id HAVING cnt > 1""",
        (source_id,),
    )
    dupes = await cursor.fetchall()
    if dupes:
        print(f"  Found {len(dupes)} duplicate post IDs:")
        for d in dupes[:10]:
            print(f"    post_id={d[0]}, count={d[1]}")
    else:
        print("  No duplicate posts found")

    print("\n" + "=" * 60)
    await db.close()


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Verify scraper data coverage and Qdrant sync.")
    parser.add_argument(
        "--qdrant-url",
        type=str,
        default=None,
        help=(
            "Qdrant server URL (e.g. http://localhost:6333). "
            "If omitted, falls back to QDRANT_URL env var or local file storage."
        ),
    )
    args = parser.parse_args()
    asyncio.run(run_verification(qdrant_url=args.qdrant_url))


if __name__ == "__main__":
    main()
