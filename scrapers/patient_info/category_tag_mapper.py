from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from scrapers.patient_info.config import CACHE_DIR
from scrapers.patient_info.logger import get_logger

logger = get_logger("mapper")

MAPPINGS_FILE = Path(__file__).resolve().parent / "mappings.json"
CATEGORIES_CACHE = CACHE_DIR / "categories.json"
TAGS_CACHE = CACHE_DIR / "tags.json"


class CategoryTagMapper:
    def __init__(self) -> None:
        self._mappings: dict[str, dict[str, Any]] = {}
        self._categories: list[dict] = []
        self._tags: list[dict] = []

    def load_mappings(self) -> None:
        with open(MAPPINGS_FILE) as f:
            self._mappings = json.load(f)
        logger.info("Loaded mappings for %d disease labels", len(self._mappings))

    async def fetch_and_cache(self, client: Any) -> None:
        """Fetch categories and tags from API via the discourse client, cache locally."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        if CATEGORIES_CACHE.exists():
            with open(CATEGORIES_CACHE) as f:
                self._categories = json.load(f)
            logger.info("Loaded %d categories from cache", len(self._categories))
        else:
            self._categories = await client.get_categories()
            with open(CATEGORIES_CACHE, "w") as f:
                json.dump(self._categories, f, indent=2)
            logger.info("Fetched and cached %d categories", len(self._categories))

        if TAGS_CACHE.exists():
            with open(TAGS_CACHE) as f:
                self._tags = json.load(f)
            logger.info("Loaded %d tags from cache", len(self._tags))
        else:
            self._tags = await client.get_tags()
            with open(TAGS_CACHE, "w") as f:
                json.dump(self._tags, f, indent=2)
            logger.info("Fetched and cached %d tags", len(self._tags))

    def get_all_labels(self) -> list[str]:
        return list(self._mappings.keys())

    def get_tag_slugs(self, label: str) -> list[str]:
        label_lower = label.lower()
        mapping = self._mappings.get(label_lower)
        if mapping:
            return mapping.get("tag_slugs", [])
        return []

    def get_tag_ids(self, label: str) -> list[int]:
        label_lower = label.lower()
        mapping = self._mappings.get(label_lower)
        if mapping:
            return mapping.get("tag_ids", [])
        return []

    def get_category_id(self, label: str) -> int | None:
        label_lower = label.lower()
        mapping = self._mappings.get(label_lower)
        if mapping:
            return mapping.get("category_id")
        return None

    def get_category_slug(self, label: str) -> str | None:
        label_lower = label.lower()
        mapping = self._mappings.get(label_lower)
        if mapping:
            return mapping.get("category_slug")
        return None

    def get_medical_category(self, label: str) -> str:
        """Get the site category name for a disease label."""
        cat_id = self.get_category_id(label)
        if cat_id and self._categories:
            for cat in self._categories:
                cid = cat.get("id") if isinstance(cat, dict) else getattr(cat, "id", None)
                if cid == cat_id:
                    return cat.get("name", "") if isinstance(cat, dict) else getattr(cat, "name", "")
        return ""
