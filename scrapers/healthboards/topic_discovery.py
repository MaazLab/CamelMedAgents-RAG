from __future__ import annotations
import json

from scrapers.healthboards.board_mapper import BoardMapper
from scrapers.healthboards.content_processor import extract_text_from_vbulletin_html
from scrapers.healthboards.database import Database
from scrapers.healthboards.healthboards_client import HealthBoardsClient
from scrapers.healthboards.logger import get_logger

logger = get_logger("hb_discovery")


class TopicDiscovery:
    def __init__(
        self,
        client: HealthBoardsClient,
        db: Database,
        mapper: BoardMapper,
        source_id: int,
    ) -> None:
        self.client = client
        self.db = db
        self.mapper = mapper
        self.source_id = source_id

    # -- Discovery --

    async def discover_topics_for_label(
        self, label: str, max_topics: int | None = None
    ) -> int:
        """Discover topics for a disease label via board pagination. Returns count of new topics."""
        board_id = self.mapper.get_board_id(label)
        if board_id is None:
            logger.warning("No board mapping for label '%s', skipping discovery", label)
            return 0
        board_name = self.mapper.get_board_name(label)
        medical_category = self.mapper.get_medical_category(label)
        scope_id = str(board_id)

        progress = await self.db.get_scrape_progress(self.source_id, "board", scope_id)
        if progress and progress["completed"]:
            logger.info("Board %d (%s) already fully discovered, skipping", board_id, board_name)
            return 0

        start_page = (progress["last_page"] + 1) if progress else 1
        total_new = 0
        page = start_page

        logger.info(
            "Discovering topics for label '%s' from board %d (%s) page %d",
            label, board_id, board_name, page,
        )

        while True:
            threads, has_more = await self.client.get_board_threads(board_id, page=page)

            if not threads:
                await self.db.update_scrape_progress(
                    self.source_id, "board", scope_id, page, completed=True
                )
                logger.info("Board %d discovery complete at page %d (no threads)", board_id, page)
                break

            for thread in threads:
                inserted = await self.db.insert_topic(
                    source_id=self.source_id,
                    platform_topic_id=thread.thread_id,
                    title=thread.title,
                    category_id=board_id,
                    category_name=board_name,
                    tags=[],
                    disease_label=label,
                    medical_category=medical_category,
                    post_count=thread.reply_count + 1,  # replies + OP
                    view_count=thread.view_count,
                    created_at_source=thread.last_post_date,
                )
                if inserted:
                    total_new += 1

            await self.db.update_scrape_progress(self.source_id, "board", scope_id, page)

            if max_topics and total_new >= max_topics:
                logger.info("Reached max_topics=%d for board %d", max_topics, board_id)
                break

            if not has_more:
                await self.db.update_scrape_progress(
                    self.source_id, "board", scope_id, page, completed=True
                )
                logger.info("Board %d discovery complete at page %d", board_id, page)
                break

            page += 1

        logger.info("Discovered %d new topics for label '%s'", total_new, label)
        return total_new

    # -- Content Scraping --

    async def scrape_topic(self, topic_row: dict) -> bool:
        """Scrape all posts for a single topic. Returns True on success.

        Uses per-page checkpointing via scrape_progress (scope_type='topic')
        so that a multi-page topic resumes from the last completed page on restart.
        """
        platform_topic_id = topic_row["platform_topic_id"]
        topic_db_id = topic_row["id"]
        scope_id = str(platform_topic_id)

        try:
            # Check for existing page-level progress on this topic
            progress = await self.db.get_scrape_progress(
                self.source_id, "topic", scope_id
            )
            if progress and progress["completed"]:
                logger.debug("Topic %d already fully scraped, skipping", platform_topic_id)
                return True

            last_scraped_page = progress["last_page"] if progress else 0

            # If we haven't scraped page 1 yet, fetch it to learn total_pages
            if last_scraped_page < 1:
                first_page = await self.client.get_thread_page(platform_topic_id, page=1)
                if first_page is None:
                    await self.db.update_topic_status(self.source_id, platform_topic_id, "failed")
                    return False

                total_pages = first_page.total_pages

                for post in first_page.posts:
                    clean_text = extract_text_from_vbulletin_html(post.html_content)
                    await self.db.insert_post(
                        source_id=self.source_id,
                        topic_db_id=topic_db_id,
                        platform_post_id=post.post_id,
                        platform_topic_id=platform_topic_id,
                        post_number=post.post_number,
                        reply_to_post_number=post.reply_to_post_number,
                        is_original_post=(post.post_number == 1),
                        username=post.author,
                        post_text=clean_text,
                        html_content=post.html_content,
                        word_count=len(clean_text.split()),
                        created_at_source=post.post_date,
                    )

                await self.db.update_scrape_progress(
                    self.source_id, "topic", scope_id, 1,
                    completed=(total_pages == 1),
                )
                last_scraped_page = 1
            else:
                # We already have page 1+; fetch page 1 just to get total_pages
                first_page = await self.client.get_thread_page(platform_topic_id, page=1)
                total_pages = first_page.total_pages if first_page else 1

            # Fetch remaining pages from where we left off
            for page_num in range(last_scraped_page + 1, total_pages + 1):
                thread_page = await self.client.get_thread_page(platform_topic_id, page=page_num)
                if thread_page is None:
                    logger.warning(
                        "Topic %d: page %d returned None, stopping",
                        platform_topic_id, page_num,
                    )
                    break

                for post in thread_page.posts:
                    clean_text = extract_text_from_vbulletin_html(post.html_content)
                    await self.db.insert_post(
                        source_id=self.source_id,
                        topic_db_id=topic_db_id,
                        platform_post_id=post.post_id,
                        platform_topic_id=platform_topic_id,
                        post_number=post.post_number,
                        reply_to_post_number=post.reply_to_post_number,
                        is_original_post=(post.post_number == 1),
                        username=post.author,
                        post_text=clean_text,
                        html_content=post.html_content,
                        word_count=len(clean_text.split()),
                        created_at_source=post.post_date,
                    )

                is_last = (page_num == total_pages)
                await self.db.update_scrape_progress(
                    self.source_id, "topic", scope_id, page_num,
                    completed=is_last,
                )

            await self.db.update_topic_status(self.source_id, platform_topic_id, "scraped")
            logger.debug("Scraped topic %d (%d pages)", platform_topic_id, total_pages)
            return True

        except Exception as e:
            logger.error("Failed to scrape topic %d: %s", platform_topic_id, e, exc_info=True)
            await self.db.update_topic_status(self.source_id, platform_topic_id, "failed")
            return False
