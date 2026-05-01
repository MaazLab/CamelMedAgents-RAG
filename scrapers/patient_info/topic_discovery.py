from __future__ import annotations
import json
from typing import Any

import httpx

from scrapers.patient_info.category_tag_mapper import CategoryTagMapper
from scrapers.patient_info.content_processor import extract_text_from_html
from scrapers.patient_info.database import Database
from scrapers.patient_info.discourse_client import DiscourseClient
from scrapers.patient_info.logger import get_logger

logger = get_logger("discovery")


class TopicDiscovery:
    def __init__(
        self,
        client: DiscourseClient,
        db: Database,
        mapper: CategoryTagMapper,
        source_id: int,
    ) -> None:
        self.client = client
        self.db = db
        self.mapper = mapper
        self.source_id = source_id

    # -- Discovery --

    _TAG_404 = -1  # sentinel: tag returned HTTP 404

    async def discover_topics_for_label(
        self, label: str, max_topics: int | None = None
    ) -> int:
        """Discover topics for a disease label. Returns count of newly discovered topics."""
        tag_slugs = self.mapper.get_tag_slugs(label)
        total_new = 0
        tag_failed_404 = False

        if tag_slugs:
            for slug in tag_slugs:
                count = await self._discover_by_tag(label, slug, max_topics)
                if count == self._TAG_404:
                    tag_failed_404 = True
                    break
                total_new += count
                if max_topics and total_new >= max_topics:
                    break

        # Fallback to category discovery when no tags exist OR tag returned 404
        if not tag_slugs or tag_failed_404:
            cat_id = self.mapper.get_category_id(label)
            cat_slug = self.mapper.get_category_slug(label)
            if cat_id and cat_slug:
                if tag_failed_404:
                    logger.warning(
                        "Tag discovery returned 404 for label '%s', "
                        "falling back to category '%s' (id=%d)",
                        label, cat_slug, cat_id,
                    )
                total_new = await self._discover_by_category(label, cat_slug, cat_id, max_topics)

        logger.info("Discovered %d new topics for label '%s'", total_new, label)
        return total_new

    async def _discover_by_tag(
        self, label: str, tag_slug: str, max_topics: int | None = None
    ) -> int:
        progress = await self.db.get_scrape_progress(self.source_id, "tag", tag_slug)
        if progress and progress["completed"]:
            logger.info("Tag '%s' already fully discovered, skipping", tag_slug)
            return 0

        start_page = (progress["last_page"] + 1) if progress else 0
        total_new = 0
        page = start_page
        medical_category = self.mapper.get_medical_category(label)

        logger.info("Discovering topics for tag '%s' from page %d", tag_slug, page)

        while True:
            try:
                data = await self.client.get_tag_topics(tag_slug, page=page)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    logger.warning("Tag '%s' returned HTTP 404", tag_slug)
                    return self._TAG_404
                raise
            topic_list = data.get("topic_list", {})
            topics = topic_list.get("topics", [])

            if not topics:
                await self.db.update_scrape_progress(self.source_id, "tag", tag_slug, page, completed=True)
                logger.info("Tag '%s' discovery complete at page %d", tag_slug, page)
                break

            for topic_data in topics:
                inserted = await self._insert_topic(topic_data, label, medical_category)
                if inserted:
                    total_new += 1

            await self.db.update_scrape_progress(self.source_id, "tag", tag_slug, page)

            if max_topics and total_new >= max_topics:
                logger.info("Reached max_topics=%d for tag '%s'", max_topics, tag_slug)
                break

            more_url = topic_list.get("more_topics_url")
            if not more_url:
                await self.db.update_scrape_progress(self.source_id, "tag", tag_slug, page, completed=True)
                logger.info("Tag '%s' discovery complete at page %d (no more pages)", tag_slug, page)
                break

            page += 1

        return total_new

    async def _discover_by_category(
        self, label: str, cat_slug: str, cat_id: int, max_topics: int | None = None
    ) -> int:
        progress = await self.db.get_scrape_progress(self.source_id, "category", str(cat_id))
        if progress and progress["completed"]:
            logger.info("Category '%s' already fully discovered, skipping", cat_slug)
            return 0

        start_page = (progress["last_page"] + 1) if progress else 0
        total_new = 0
        page = start_page
        medical_category = self.mapper.get_medical_category(label)

        logger.info("Discovering topics for category '%s' (id=%d) from page %d", cat_slug, cat_id, page)

        while True:
            data = await self.client.get_category_topics(cat_slug, cat_id, page=page)
            topic_list = data.get("topic_list", {})
            topics = topic_list.get("topics", [])

            if not topics:
                await self.db.update_scrape_progress(self.source_id, "category", str(cat_id), page, completed=True)
                break

            for topic_data in topics:
                inserted = await self._insert_topic(topic_data, label, medical_category)
                if inserted:
                    total_new += 1

            await self.db.update_scrape_progress(self.source_id, "category", str(cat_id), page)

            if max_topics and total_new >= max_topics:
                break

            more_url = topic_list.get("more_topics_url")
            if not more_url:
                await self.db.update_scrape_progress(self.source_id, "category", str(cat_id), page, completed=True)
                break

            page += 1

        return total_new

    async def _insert_topic(self, topic_data: dict, label: str, medical_category: str) -> bool:
        topic_id = topic_data.get("id")
        if not topic_id:
            return False

        tags = topic_data.get("tags", [])
        if isinstance(tags, list) and tags and isinstance(tags[0], dict):
            tags = [t.get("name", "") for t in tags]

        result = await self.db.insert_topic(
            source_id=self.source_id,
            platform_topic_id=topic_id,
            title=topic_data.get("title", ""),
            category_id=topic_data.get("category_id"),
            category_name="",
            tags=tags,
            disease_label=label,
            medical_category=medical_category,
            post_count=topic_data.get("posts_count", 0),
            view_count=topic_data.get("views", 0),
            created_at_source=topic_data.get("created_at", ""),
        )
        return result is not None

    # -- Content Scraping --

    async def scrape_topic(self, topic_row: dict) -> bool:
        """Scrape all posts for a single topic. Returns True on success."""
        platform_topic_id = topic_row["platform_topic_id"]
        topic_db_id = topic_row["id"]

        try:
            topic_data = await self.client.get_topic(platform_topic_id)
            if not topic_data:
                await self.db.update_topic_status(self.source_id, platform_topic_id, "failed")
                return False

            post_stream = topic_data.get("post_stream", {})
            inline_posts = post_stream.get("posts", [])
            all_post_ids = post_stream.get("stream", [])

            # Process inline posts (first ~20)
            for post_data in inline_posts:
                await self._insert_post(post_data, topic_db_id, platform_topic_id)

            # Fetch remaining posts if topic has >20
            inline_ids = {p["id"] for p in inline_posts}
            remaining_ids = [pid for pid in all_post_ids if pid not in inline_ids]

            if remaining_ids:
                logger.debug(
                    "Topic %d has %d additional posts to fetch",
                    platform_topic_id, len(remaining_ids),
                )
                # Fetch in batches of 20
                for i in range(0, len(remaining_ids), 20):
                    batch = remaining_ids[i : i + 20]
                    extra_posts = await self.client.get_topic_posts(platform_topic_id, batch)
                    for post_data in extra_posts:
                        await self._insert_post(post_data, topic_db_id, platform_topic_id)

            await self.db.update_topic_status(self.source_id, platform_topic_id, "scraped")
            logger.debug("Scraped topic %d (%d posts)", platform_topic_id, len(all_post_ids))
            return True

        except Exception as e:
            logger.error("Failed to scrape topic %d: %s", platform_topic_id, e)
            await self.db.update_topic_status(self.source_id, platform_topic_id, "failed")
            return False

    async def _insert_post(self, post_data: dict, topic_db_id: int, platform_topic_id: int) -> None:
        html_content = post_data.get("cooked", "")
        clean_text = extract_text_from_html(html_content)
        post_number = post_data.get("post_number", 0)

        await self.db.insert_post(
            source_id=self.source_id,
            topic_db_id=topic_db_id,
            platform_post_id=post_data.get("id", 0),
            platform_topic_id=platform_topic_id,
            post_number=post_number,
            reply_to_post_number=post_data.get("reply_to_post_number"),
            is_original_post=(post_number == 1),
            username=post_data.get("username", ""),
            post_text=clean_text,
            html_content=html_content,
            word_count=post_data.get("word_count") or len(clean_text.split()),
            created_at_source=post_data.get("created_at", ""),
        )
