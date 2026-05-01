#!/usr/bin/env python3
"""CLI entry point for the healthboards.com vBulletin forum scraper."""
from __future__ import annotations
import argparse
import asyncio
import sys

from scrapers.healthboards.logger import setup_logging, get_logger
from scrapers.healthboards.pipeline import Pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape www.healthboards.com medical forum topics into SQLite.",
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
        help="Discover topics only — skip scraping, embedding, and matching.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        default=False,
        help="Start from scratch, ignoring saved progress.",
    )
    parser.add_argument(
        "--qdrant-url",
        type=str,
        default=None,
        help="Qdrant server URL (e.g. http://localhost:6333). Default: from config.",
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
    parser.add_argument(
        "--headless",
        type=lambda x: x.lower() in ("true", "1", "yes"),
        default=False,
        help="Run Playwright browser in headless mode. Default: false (headed mode is more reliable against Cloudflare).",
    )
    parser.add_argument(
        "--browser-timeout",
        type=int,
        default=90,
        help="Page load timeout in seconds. Default: 90.",
    )
    return parser.parse_args()


def main() -> None:
    setup_logging()
    logger = get_logger("cli")

    args = parse_args()

    labels = [l.lower() for l in args.labels] if args.labels else None

    pipeline = Pipeline(
        labels=labels,
        max_topics_per_label=args.max_topics_per_label,
        dry_run=args.dry_run,
        qdrant_url=args.qdrant_url,
        jsonl_path=args.jsonl_path,
        embedding_model=args.embedding_model,
        headless=args.headless,
        browser_timeout=args.browser_timeout * 1000,  # convert to ms
    )

    logger.info(
        "Starting healthboards scraper — labels=%s, max_topics=%s, dry_run=%s, "
        "headless=%s, browser_timeout=%ds",
        labels or "all",
        args.max_topics_per_label,
        args.dry_run,
        args.headless,
        args.browser_timeout,
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
