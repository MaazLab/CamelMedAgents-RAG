from __future__ import annotations
import hashlib
import json
import aiosqlite
from pathlib import Path
from typing import Optional

from scrapers.patient_info.config import DB_PATH
from scrapers.patient_info.logger import get_logger

logger = get_logger("database")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    base_url    TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS topics (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id           INTEGER NOT NULL REFERENCES sources(id),
    platform_topic_id   INTEGER NOT NULL,
    title               TEXT,
    category_id         INTEGER,
    category_name       TEXT,
    tags                TEXT,
    disease_label       TEXT,
    medical_category    TEXT,
    post_count          INTEGER,
    view_count          INTEGER,
    created_at_source   TEXT,
    scrape_status       TEXT DEFAULT 'discovered',
    scraped_at          TEXT,
    UNIQUE(source_id, platform_topic_id)
);

CREATE TABLE IF NOT EXISTS posts (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id               INTEGER NOT NULL REFERENCES sources(id),
    topic_id                INTEGER NOT NULL REFERENCES topics(id),
    platform_post_id        INTEGER NOT NULL,
    platform_topic_id       INTEGER NOT NULL,
    post_number             INTEGER,
    reply_to_post_number    INTEGER,
    is_original_post        BOOLEAN,
    username                TEXT,
    post_text               TEXT,
    html_content            TEXT,
    word_count              INTEGER,
    created_at_source       TEXT,
    qdrant_point_id         TEXT,
    embedding_hash          TEXT,
    upserted_at             TEXT,
    UNIQUE(source_id, platform_post_id)
);

CREATE TABLE IF NOT EXISTS queries (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id                   INTEGER NOT NULL REFERENCES sources(id),
    original_text               TEXT NOT NULL,
    text_hash                   TEXT NOT NULL,
    label                       TEXT NOT NULL,
    category                    TEXT,
    symptoms_json               TEXT,
    duration_json               TEXT,
    frequency                   TEXT,
    triggers_json               TEXT,
    symptom_temporal_map_json   TEXT,
    patient_context_json        TEXT,
    clinical_interpretation_json TEXT,
    representation_text         TEXT,
    loaded_at                   TEXT DEFAULT (datetime('now')),
    UNIQUE(source_id, text_hash)
);

CREATE TABLE IF NOT EXISTS query_post_mappings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id        INTEGER NOT NULL REFERENCES queries(id),
    post_id         INTEGER NOT NULL REFERENCES posts(id),
    similarity_score REAL NOT NULL,
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(query_id, post_id)
);

CREATE TABLE IF NOT EXISTS scrape_progress (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   INTEGER NOT NULL REFERENCES sources(id),
    scope_type  TEXT NOT NULL,
    scope_id    TEXT NOT NULL,
    last_page   INTEGER DEFAULT 0,
    completed   BOOLEAN DEFAULT FALSE,
    updated_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(source_id, scope_type, scope_id)
);
"""


class Database:
    def __init__(self, db_path: Path | None = None):
        self.db_path = str(db_path or DB_PATH)
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(SCHEMA_SQL)
        await self._db.commit()

        # Migrations for evolving schema on existing databases
        try:
            await self._db.execute(
                "ALTER TABLE queries ADD COLUMN symptom_temporal_map_json TEXT"
            )
            await self._db.commit()
        except Exception:
            pass  # Column already exists

        logger.info("Database connected at %s", self.db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.commit()
            await self._db.close()
            self._db = None
            logger.debug("Database connection closed")

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._db

    # -- Sources --

    async def get_or_create_source(self, name: str, base_url: str) -> int:
        cursor = await self.db.execute(
            "SELECT id FROM sources WHERE name = ?", (name,)
        )
        row = await cursor.fetchone()
        if row:
            return row[0]

        cursor = await self.db.execute(
            "INSERT INTO sources (name, base_url) VALUES (?, ?)",
            (name, base_url),
        )
        await self.db.commit()
        source_id = cursor.lastrowid
        logger.info("Created source '%s' (id=%d)", name, source_id)
        return source_id

    # -- Topics --

    async def insert_topic(
        self,
        source_id: int,
        platform_topic_id: int,
        title: str,
        category_id: int | None,
        category_name: str,
        tags: list[str],
        disease_label: str,
        medical_category: str,
        post_count: int,
        view_count: int,
        created_at_source: str,
    ) -> int | None:
        try:
            cursor = await self.db.execute(
                """INSERT INTO topics
                   (source_id, platform_topic_id, title, category_id, category_name,
                    tags, disease_label, medical_category, post_count, view_count,
                    created_at_source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source_id, platform_topic_id, title, category_id, category_name,
                    json.dumps(tags), disease_label, medical_category,
                    post_count, view_count, created_at_source,
                ),
            )
            await self.db.commit()
            return cursor.lastrowid
        except aiosqlite.IntegrityError:
            logger.debug("Topic %d already exists for source %d", platform_topic_id, source_id)
            return None

    async def get_topic_db_id(self, source_id: int, platform_topic_id: int) -> int | None:
        cursor = await self.db.execute(
            "SELECT id FROM topics WHERE source_id = ? AND platform_topic_id = ?",
            (source_id, platform_topic_id),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def get_topic_by_db_id(self, topic_db_id: int) -> dict | None:
        cursor = await self.db.execute(
            "SELECT * FROM topics WHERE id = ?",
            (topic_db_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def update_topic_status(
        self, source_id: int, platform_topic_id: int, status: str
    ) -> None:
        await self.db.execute(
            """UPDATE topics SET scrape_status = ?,
               scraped_at = CASE WHEN ? IN ('scraped', 'failed') THEN datetime('now') ELSE scraped_at END
               WHERE source_id = ? AND platform_topic_id = ?""",
            (status, status, source_id, platform_topic_id),
        )
        await self.db.commit()

    async def get_pending_topics(
        self, source_id: int, disease_label: str | None = None, limit: int | None = None
    ) -> list[dict]:
        sql = "SELECT * FROM topics WHERE source_id = ? AND scrape_status IN ('discovered', 'failed')"
        params: list = [source_id]
        if disease_label:
            sql += " AND disease_label = ?"
            params.append(disease_label)
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        cursor = await self.db.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # -- Posts --

    async def insert_post(
        self,
        source_id: int,
        topic_db_id: int,
        platform_post_id: int,
        platform_topic_id: int,
        post_number: int,
        reply_to_post_number: int | None,
        is_original_post: bool,
        username: str,
        post_text: str,
        html_content: str,
        word_count: int,
        created_at_source: str,
    ) -> int | None:
        try:
            cursor = await self.db.execute(
                """INSERT INTO posts
                   (source_id, topic_id, platform_post_id, platform_topic_id,
                    post_number, reply_to_post_number, is_original_post,
                    username, post_text, html_content, word_count, created_at_source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source_id, topic_db_id, platform_post_id, platform_topic_id,
                    post_number, reply_to_post_number, is_original_post,
                    username, post_text, html_content, word_count, created_at_source,
                ),
            )
            await self.db.commit()
            return cursor.lastrowid
        except aiosqlite.IntegrityError:
            logger.debug("Post %d already exists for source %d", platform_post_id, source_id)
            return None

    async def get_posts_by_topic(self, topic_db_id: int) -> list[dict]:
        cursor = await self.db.execute(
            "SELECT * FROM posts WHERE topic_id = ?", (topic_db_id,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def update_post_qdrant_id(self, post_db_id: int, qdrant_point_id: str, embedding_hash: str) -> None:
        await self.db.execute(
            "UPDATE posts SET qdrant_point_id = ?, embedding_hash = ?, upserted_at = datetime('now') WHERE id = ?",
            (qdrant_point_id, embedding_hash, post_db_id),
        )
        await self.db.commit()

    async def get_posts_pending_upsert(self, source_id: int) -> list[dict]:
        cursor = await self.db.execute(
            "SELECT * FROM posts WHERE source_id = ? AND qdrant_point_id IS NULL",
            (source_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_posts_needing_reembed(self, source_id: int) -> list[dict]:
        """Get posts that have been upserted but whose content has changed (hash mismatch)."""
        cursor = await self.db.execute(
            """SELECT * FROM posts WHERE source_id = ? AND qdrant_point_id IS NOT NULL
               AND embedding_hash IS NOT NULL""",
            (source_id,),
        )
        rows = await cursor.fetchall()
        results = []
        for r in rows:
            row = dict(r)
            current_hash = hashlib.sha256((row.get("post_text") or "").encode()).hexdigest()[:16]
            if current_hash != row.get("embedding_hash"):
                results.append(row)
        return results

    async def get_thread_context(self, source_id: int) -> dict[int, list[int]]:
        """Return mapping of platform_topic_id → list of platform_post_id for all posts."""
        cursor = await self.db.execute(
            "SELECT platform_topic_id, platform_post_id FROM posts WHERE source_id = ?",
            (source_id,),
        )
        rows = await cursor.fetchall()
        result: dict[int, list[int]] = {}
        for row in rows:
            result.setdefault(row[0], []).append(row[1])
        return result

    # -- Queries --

    async def insert_query(
        self,
        source_id: int,
        original_text: str,
        label: str,
        category: str | None,
        symptoms_json: str | None,
        duration_json: str | None,
        frequency: str | None,
        triggers_json: str | None,
        symptom_temporal_map_json: str | None,
        patient_context_json: str | None,
        clinical_interpretation_json: str | None,
        representation_text: str | None,
    ) -> int | None:
        text_hash = hashlib.sha256(original_text.encode()).hexdigest()[:16]
        try:
            cursor = await self.db.execute(
                """INSERT INTO queries
                   (source_id, original_text, text_hash, label, category,
                    symptoms_json, duration_json, frequency, triggers_json,
                    symptom_temporal_map_json,
                    patient_context_json, clinical_interpretation_json, representation_text)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source_id, original_text, text_hash, label, category,
                    symptoms_json, duration_json, frequency, triggers_json,
                    symptom_temporal_map_json,
                    patient_context_json, clinical_interpretation_json, representation_text,
                ),
            )
            await self.db.commit()
            return cursor.lastrowid
        except aiosqlite.IntegrityError:
            return None

    async def get_queries_by_label(self, source_id: int, label: str) -> list[dict]:
        cursor = await self.db.execute(
            "SELECT * FROM queries WHERE source_id = ? AND label = ?",
            (source_id, label),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_all_query_labels(self, source_id: int) -> list[str]:
        cursor = await self.db.execute(
            "SELECT DISTINCT label FROM queries WHERE source_id = ?",
            (source_id,),
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def get_queries_pending_matching(self, source_id: int) -> list[dict]:
        """Get queries that have no mappings yet."""
        cursor = await self.db.execute(
            """SELECT q.* FROM queries q
               WHERE q.source_id = ?
               AND NOT EXISTS (SELECT 1 FROM query_post_mappings m WHERE m.query_id = q.id)""",
            (source_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def insert_query_post_mapping(
        self, query_id: int, post_id: int, similarity_score: float
    ) -> int | None:
        try:
            cursor = await self.db.execute(
                """INSERT INTO query_post_mappings (query_id, post_id, similarity_score)
                   VALUES (?, ?, ?)
                   ON CONFLICT(query_id, post_id)
                   DO UPDATE SET similarity_score = excluded.similarity_score""",
                (query_id, post_id, similarity_score),
            )
            await self.db.commit()
            return cursor.lastrowid
        except Exception:
            logger.debug("Failed to insert mapping query=%d post=%d", query_id, post_id)
            return None

    async def get_mappings_for_query(self, query_id: int) -> list[dict]:
        cursor = await self.db.execute(
            "SELECT * FROM query_post_mappings WHERE query_id = ? ORDER BY similarity_score DESC",
            (query_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_mapping_stats(self, source_id: int) -> dict:
        stats: dict = {}
        cursor = await self.db.execute(
            "SELECT COUNT(*) FROM queries WHERE source_id = ?", (source_id,)
        )
        stats["total_queries"] = (await cursor.fetchone())[0]

        cursor = await self.db.execute(
            """SELECT COUNT(DISTINCT m.query_id) FROM query_post_mappings m
               JOIN queries q ON m.query_id = q.id WHERE q.source_id = ?""",
            (source_id,),
        )
        stats["queries_with_matches"] = (await cursor.fetchone())[0]
        stats["queries_without_matches"] = stats["total_queries"] - stats["queries_with_matches"]

        cursor = await self.db.execute(
            """SELECT COUNT(*) FROM query_post_mappings m
               JOIN queries q ON m.query_id = q.id WHERE q.source_id = ?""",
            (source_id,),
        )
        stats["total_mappings"] = (await cursor.fetchone())[0]

        if stats["total_mappings"] > 0:
            cursor = await self.db.execute(
                """SELECT AVG(similarity_score), MIN(similarity_score), MAX(similarity_score)
                   FROM query_post_mappings m
                   JOIN queries q ON m.query_id = q.id WHERE q.source_id = ?""",
                (source_id,),
            )
            row = await cursor.fetchone()
            stats["avg_score"] = round(row[0], 4) if row[0] else 0
            stats["min_score"] = round(row[1], 4) if row[1] else 0
            stats["max_score"] = round(row[2], 4) if row[2] else 0

            cursor = await self.db.execute(
                """SELECT AVG(cnt) FROM (
                       SELECT COUNT(*) as cnt FROM query_post_mappings m
                       JOIN queries q ON m.query_id = q.id WHERE q.source_id = ?
                       GROUP BY m.query_id
                   )""",
                (source_id,),
            )
            row = await cursor.fetchone()
            stats["avg_posts_per_query"] = round(row[0], 1) if row[0] else 0

            cursor = await self.db.execute(
                """SELECT AVG(cnt) FROM (
                       SELECT COUNT(*) as cnt FROM query_post_mappings m
                       JOIN queries q ON m.query_id = q.id WHERE q.source_id = ?
                       GROUP BY m.post_id
                   )""",
                (source_id,),
            )
            row = await cursor.fetchone()
            stats["avg_queries_per_post"] = round(row[0], 1) if row[0] else 0
        else:
            stats["avg_score"] = 0
            stats["min_score"] = 0
            stats["max_score"] = 0
            stats["avg_posts_per_query"] = 0
            stats["avg_queries_per_post"] = 0

        return stats

    async def get_post_db_id_by_qdrant_point(self, qdrant_point_id: str) -> int | None:
        cursor = await self.db.execute(
            "SELECT id FROM posts WHERE qdrant_point_id = ?", (qdrant_point_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    # -- Scrape Progress --

    async def update_scrape_progress(
        self, source_id: int, scope_type: str, scope_id: str, last_page: int, completed: bool = False
    ) -> None:
        await self.db.execute(
            """INSERT INTO scrape_progress (source_id, scope_type, scope_id, last_page, completed, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(source_id, scope_type, scope_id)
               DO UPDATE SET last_page = ?, completed = ?, updated_at = datetime('now')""",
            (source_id, scope_type, scope_id, last_page, completed, last_page, completed),
        )
        await self.db.commit()

    async def get_scrape_progress(
        self, source_id: int, scope_type: str, scope_id: str
    ) -> dict | None:
        cursor = await self.db.execute(
            "SELECT * FROM scrape_progress WHERE source_id = ? AND scope_type = ? AND scope_id = ?",
            (source_id, scope_type, scope_id),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    # -- Stats --

    async def get_stats(self, source_id: int) -> dict:
        stats = {}

        cursor = await self.db.execute(
            "SELECT scrape_status, COUNT(*) FROM topics WHERE source_id = ? GROUP BY scrape_status",
            (source_id,),
        )
        stats["topics"] = {row[0]: row[1] for row in await cursor.fetchall()}

        cursor = await self.db.execute(
            "SELECT COUNT(*) FROM posts WHERE source_id = ?",
            (source_id,),
        )
        stats["total_posts"] = (await cursor.fetchone())[0]

        cursor = await self.db.execute(
            "SELECT COUNT(*) FROM posts WHERE source_id = ? AND qdrant_point_id IS NOT NULL",
            (source_id,),
        )
        stats["upserted_to_qdrant"] = (await cursor.fetchone())[0]

        return stats
