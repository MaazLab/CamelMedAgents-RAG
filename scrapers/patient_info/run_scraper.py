#!/usr/bin/env python3
"""CLI entry point for the patient.info community forum scraper."""
from __future__ import annotations
import argparse
import asyncio
import sys

from scrapers.patient_info.logger import setup_logging, get_logger
from scrapers.patient_info.pipeline import Pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape community.patient.info medical forum topics into SQLite.",
    )
    parser.add_argument(
        "--labels",
        nargs="+",
        default=None,
        help="Disease labels to scrape (e.g. 'acne' 'diabetes'). Default: all 20 labels.",
    )
    parser.add_argument(
        "--max-topics-per-label",
        type=int,
        default=None,
        help="Maximum topics to discover per label. Default: unlimited.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover only — skip content scraping.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="Resume from last saved progress (default: True).",
    )
    parser.add_argument(
        "--qdrant-url",
        type=str,
        default=None,
        help=(
            "Qdrant server URL (e.g. http://localhost:6333). "
            "If omitted, falls back to QDRANT_URL env var or local file storage."
        ),
    )
    parser.add_argument(
        "--jsonl-path",
        type=str,
        default=None,
        help="Path to structured queries JSONL file. Default: from config.",
    )
    parser.add_argument(
        "--embedding-model",
        type=str,
        default=None,
        help="Sentence-transformer model name. Default: all-MiniLM-L6-v2.",
    )
    return parser.parse_args()


def main() -> None:
    setup_logging()
    logger = get_logger("cli")

    args = parse_args()

    labels = [l.lower() for l in args.labels] if args.labels else None

    kwargs = {
        "labels": labels,
        "max_topics_per_label": args.max_topics_per_label,
        "dry_run": args.dry_run,
        "qdrant_url": args.qdrant_url,
        "jsonl_path": args.jsonl_path,
        "embedding_model": args.embedding_model,
    }

    pipeline = Pipeline(**kwargs)

    logger.info(
        "Starting scraper — labels=%s, max_topics=%s, dry_run=%s, qdrant_url=%s, embedding_model=%s",
        labels or "all", args.max_topics_per_label, args.dry_run,
        args.qdrant_url or "(local file storage)",
        args.embedding_model or "(default)",
    )

    try:
        asyncio.run(pipeline.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception("Pipeline failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
