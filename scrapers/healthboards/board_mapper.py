from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from scrapers.healthboards.logger import get_logger

logger = get_logger("board_mapper")

MAPPINGS_FILE = Path(__file__).resolve().parent / "mappings.json"


class BoardMapper:
    def __init__(self) -> None:
        self._mappings: dict[str, dict[str, Any]] = {}

    def load_mappings(self) -> None:
        with open(MAPPINGS_FILE) as f:
            self._mappings = json.load(f)
        logger.info("Loaded board mappings for %d disease labels", len(self._mappings))

    def _resolve(self, label: str) -> dict[str, Any] | None:
        """Look up mapping entry, trying the label as-is first, then normalized."""
        key = label.lower()
        entry = self._mappings.get(key)
        if entry is not None:
            return entry
        # Fallback: try replacing hyphens↔spaces and &↔and
        alt = key.replace("-", " ").replace(" and ", " & ")
        entry = self._mappings.get(alt)
        if entry is not None:
            return entry
        alt2 = key.replace(" ", "-").replace("-&-", "-and-")
        return self._mappings.get(alt2)

    def get_all_labels(self) -> list[str]:
        return list(self._mappings.keys())

    def has_label(self, label: str) -> bool:
        return self._resolve(label) is not None

    def get_board_id(self, label: str) -> int | None:
        entry = self._resolve(label)
        return entry["board_id"] if entry else None

    def get_board_slug(self, label: str) -> str | None:
        entry = self._resolve(label)
        return entry["board_slug"] if entry else None

    def get_board_name(self, label: str) -> str | None:
        entry = self._resolve(label)
        return entry["board_name"] if entry else None

    def get_medical_category(self, label: str) -> str | None:
        entry = self._resolve(label)
        return entry["medical_category"] if entry else None
