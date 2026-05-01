from __future__ import annotations
import asyncio
from typing import Any

import httpx

from scrapers.patient_info.config import (
    DISCOURSE_BASE_URL,
    USER_AGENT,
    RATE_LIMIT_DELAY,
    RETRY_MAX_ATTEMPTS,
    RETRY_BACKOFF_FACTOR,
    RETRY_STATUS_CODES,
    REQUEST_TIMEOUT,
)
from scrapers.patient_info.logger import get_logger

logger = get_logger("client")

BLOCKED_PATHS = ["/search"]


class DiscourseClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or DISCOURSE_BASE_URL).rstrip("/")
        self._client: httpx.AsyncClient | None = None
        self._last_request_time: float = 0.0

    async def __aenter__(self) -> DiscourseClient:
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _rate_limit(self) -> None:
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            wait = RATE_LIMIT_DELAY - elapsed
            logger.debug("Rate limit: waiting %.2fs", wait)
            await asyncio.sleep(wait)
        self._last_request_time = asyncio.get_event_loop().time()

    def _check_robots(self, path: str) -> None:
        for blocked in BLOCKED_PATHS:
            if path.startswith(blocked):
                raise ValueError(f"Path '{path}' is disallowed by robots.txt")

    async def _get(self, path: str, params: dict | None = None) -> Any:
        self._check_robots(path)

        if self._client is None:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
            await self._rate_limit()

            try:
                response = await self._client.get(path, params=params)

                if response.status_code == 200:
                    return response.json()

                if response.status_code in RETRY_STATUS_CODES and attempt < RETRY_MAX_ATTEMPTS:
                    wait = RETRY_BACKOFF_FACTOR ** attempt
                    logger.warning(
                        "HTTP %d on %s (attempt %d/%d), retrying in %.1fs",
                        response.status_code, path, attempt, RETRY_MAX_ATTEMPTS, wait,
                    )
                    await asyncio.sleep(wait)
                    continue

                response.raise_for_status()

            except httpx.TimeoutException:
                if attempt < RETRY_MAX_ATTEMPTS:
                    wait = RETRY_BACKOFF_FACTOR ** attempt
                    logger.warning(
                        "Timeout on %s (attempt %d/%d), retrying in %.1fs",
                        path, attempt, RETRY_MAX_ATTEMPTS, wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                raise

        return None  # should not reach here

    # -- API Methods --

    async def get_categories(self) -> list[dict]:
        data = await self._get("/categories.json")
        return data.get("category_list", {}).get("categories", [])

    async def get_tags(self) -> list[dict]:
        data = await self._get("/tags.json")
        return data.get("tags", [])

    async def get_category_topics(self, category_slug: str, category_id: int, page: int = 0) -> dict:
        data = await self._get(f"/c/{category_slug}/{category_id}.json", params={"page": page})
        return data or {}

    async def get_tag_topics(self, tag_slug: str, page: int = 0) -> dict:
        data = await self._get(f"/tag/{tag_slug}.json", params={"page": page})
        return data or {}

    async def get_topic(self, topic_id: int) -> dict:
        data = await self._get(f"/t/{topic_id}.json")
        return data or {}

    async def get_topic_posts(self, topic_id: int, post_ids: list[int]) -> list[dict]:
        if not post_ids:
            return []
        params = {f"post_ids[]": post_ids}
        data = await self._get(f"/t/{topic_id}/posts.json", params=params)
        if data:
            return data.get("post_stream", {}).get("posts", [])
        return []
