from __future__ import annotations
import json
import uuid
from typing import Any

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    ScoredPoint,
    VectorParams,
)

from scrapers.patient_info.config import (
    DISCOURSE_BASE_URL,
    EMBEDDING_DIM,
    QDRANT_MAX_REQUEST_SIZE_MB,
    QDRANT_URL,
    QDRANT_COLLECTION_NAME,
)
from scrapers.patient_info.logger import get_logger

logger = get_logger("vector_store")

_POINT_ID_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

# Leave a 20 % safety margin below Qdrant's configured HTTP limit.
# Qdrant default: service.max_request_size_mb = 32.
# QDRANT_MAX_REQUEST_SIZE_MB mirrors that setting so both sides stay in sync.
_MAX_UPSERT_BYTES = int(QDRANT_MAX_REQUEST_SIZE_MB * 1024 * 1024 * 0.80)


def _point_json_bytes(point: PointStruct) -> int:
    """Return the serialised JSON byte length of a single PointStruct."""
    try:
        return len(point.model_dump_json().encode())  # pydantic v2
    except AttributeError:
        return len(point.json().encode())             # pydantic v1


def _iter_sized_chunks(points: list[PointStruct]):
    """Yield sub-lists of PointStructs where each list's JSON stays under _MAX_UPSERT_BYTES.

    This is size-driven, not count-driven, so it handles variable-length
    post_text and thread_point_ids without ever hitting the server limit.
    """
    current: list[PointStruct] = []
    current_bytes = 2  # JSON array brackets: []
    for point in points:
        point_bytes = _point_json_bytes(point) + 1  # +1 for the comma separator
        if current and current_bytes + point_bytes > _MAX_UPSERT_BYTES:
            yield current
            current = [point]
            current_bytes = 2 + point_bytes
        else:
            current.append(point)
            current_bytes += point_bytes
    if current:
        yield current


def generate_point_id(source: str, platform_post_id: int) -> str:
    return str(uuid.uuid5(_POINT_ID_NAMESPACE, f"{source}:{platform_post_id}"))


def _build_payload(
    post_row: dict,
    topic_row: dict,
    source: str = DISCOURSE_BASE_URL,
    matched_queries: list[dict] | None = None,
    thread_post_count: int = 0,
    thread_point_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Build the Qdrant point payload from a post and its parent topic.

    Payload field reference
    -----------------------
    source              : Base URL of the data source (e.g. 'https://community.patient.info').

    platform_topic_id   : Discourse topic (thread) ID on the source forum.

    platform_post_id    : Discourse post (reply) ID — unique per individual message.

    post_number         : Sequential position of this post within its thread (1 = original question).

    reply_to_post_number: post_number this reply directly responds to; None = general thread reply.

    is_original_post    : True only when post_number == 1 (the opening question of the thread).

    title               : Thread title from the parent topic — shared by all posts in the same thread.

    post_text           : Clean plain text of the post after HTML stripping.
                          This is the text that was embedded to produce the vector for this point.

    username            : Anonymised Discourse username of the post author.

    disease_label       : One of the 20 disease labels. Primary filter field in semantic search.

    medical_category    : Broad medical category from mappings.json.

    category_name       : Discourse forum's own category name. Empty when discovered via tag browsing.

    tags                : List of Discourse tags on the thread.

    created_at          : ISO 8601 timestamp of when this post was made on the forum.

    word_count          : Number of words in post_text after HTML cleaning.

    thread_post_count   : Total number of posts in the same thread (topic). Enables retrieval of
                          the full conversation context for RAG.

    thread_point_ids    : List of Qdrant point IDs for every post in the same thread. Enables
                          fetching the complete thread from Qdrant in a single call.

    matched_queries     : List of full query parameter dicts for queries semantically matched to
                          this post. Each entry contains: query_id, original_text, label, category,
                          symptoms, duration, frequency, triggers, symptom_temporal_map,
                          patient_context, clinical_interpretation, representation_text,
                          similarity_score. Populated in Stage 4 by query_matcher.py.
                          Empty until matching runs.
    """
    tags = topic_row.get("tags", [])
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except Exception:
            tags = []

    return {
        "source": source,  # base URL of the forum; identifies datasource across scrapers
        "platform_topic_id": post_row["platform_topic_id"],
        "platform_post_id": post_row["platform_post_id"],
        "post_number": post_row.get("post_number", 0),
        "reply_to_post_number": post_row.get("reply_to_post_number"),
        "is_original_post": bool(post_row.get("is_original_post")),
        "title": topic_row.get("title", ""),
        "post_text": post_row.get("post_text", ""),
        "username": post_row.get("username", ""),
        "disease_label": topic_row.get("disease_label", ""),
        "medical_category": topic_row.get("medical_category", ""),
        "category_name": topic_row.get("category_name", ""),
        "tags": tags,
        "created_at": post_row.get("created_at_source", ""),
        "word_count": post_row.get("word_count", 0),
        "thread_post_count": thread_post_count,
        "thread_point_ids": thread_point_ids or [],
        "matched_queries": matched_queries or [],
    }


class VectorStore:
    def __init__(
        self,
        qdrant_url: str | None = None,
        collection_name: str = QDRANT_COLLECTION_NAME,
        embedding_dim: int | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.embedding_dim = embedding_dim or EMBEDDING_DIM
        url = qdrant_url or QDRANT_URL
        logger.info("Connecting to Qdrant server at %s", url)
        self._client = QdrantClient(url=url)

    def ensure_collection(self) -> None:
        existing = [c.name for c in self._client.get_collections().collections]

        if self.collection_name not in existing:
            self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.embedding_dim, distance=Distance.COSINE
                ),
            )
            logger.info(
                "Created collection '%s' (dim=%d, cosine)",
                self.collection_name, self.embedding_dim,
            )

            for field, schema_type in [
                ("source", PayloadSchemaType.KEYWORD),
                ("disease_label", PayloadSchemaType.KEYWORD),
                ("medical_category", PayloadSchemaType.KEYWORD),
                ("is_original_post", PayloadSchemaType.BOOL),
                ("platform_topic_id", PayloadSchemaType.INTEGER),
                ("platform_post_id", PayloadSchemaType.INTEGER),
            ]:
                self._client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema=schema_type,
                )
            logger.info("Created payload indexes on collection '%s'", self.collection_name)
        else:
            logger.info("Collection '%s' already exists", self.collection_name)

    def upsert_post(
        self,
        post_row: dict,
        topic_row: dict,
        embedding_vector: np.ndarray | list[float],
        source: str = DISCOURSE_BASE_URL,
        matched_queries: list[dict] | None = None,
        thread_post_count: int = 0,
        thread_point_ids: list[str] | None = None,
    ) -> str:
        """Upsert a single post with its real embedding vector. Returns the point ID."""
        point_id = generate_point_id(source, post_row["platform_post_id"])
        payload = _build_payload(
            post_row, topic_row,
            source=source,
            matched_queries=matched_queries,
            thread_post_count=thread_post_count,
            thread_point_ids=thread_point_ids,
        )

        vector = embedding_vector.tolist() if isinstance(embedding_vector, np.ndarray) else embedding_vector

        self._client.upsert(
            collection_name=self.collection_name,
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )
        logger.debug("Upserted post %d (point_id=%s)", post_row["platform_post_id"], point_id)
        return point_id

    def upsert_batch(
        self,
        posts_with_topics: list[tuple[dict, dict]],
        embedding_vectors: np.ndarray | list[list[float]],
        source: str = DISCOURSE_BASE_URL,
        matched_queries_list: list[list[dict]] | None = None,
        thread_contexts: list[dict] | None = None,
    ) -> list[str]:
        """Upsert a batch of (post_row, topic_row) with their embedding vectors."""
        points = []
        point_ids = []

        for i, (post_row, topic_row) in enumerate(posts_with_topics):
            point_id = generate_point_id(source, post_row["platform_post_id"])
            point_ids.append(point_id)

            mqs = matched_queries_list[i] if matched_queries_list else None
            tc = thread_contexts[i] if thread_contexts else {}
            payload = _build_payload(
                post_row, topic_row,
                source=source,
                matched_queries=mqs,
                thread_post_count=tc.get("thread_post_count", 0),
                thread_point_ids=tc.get("thread_point_ids"),
            )

            vec = embedding_vectors[i]
            vector = vec.tolist() if isinstance(vec, np.ndarray) else vec

            points.append(PointStruct(id=point_id, vector=vector, payload=payload))

        if points:
            for chunk in _iter_sized_chunks(points):
                self._client.upsert(collection_name=self.collection_name, points=chunk)
            logger.debug("Batch upserted %d posts to Qdrant", len(points))
        return point_ids

    def search_similar(
        self,
        query_vector: np.ndarray | list[float],
        disease_label: str,
        top_k: int = 50,
        score_threshold: float = 0.5,
    ) -> list[ScoredPoint]:
        """Search for posts similar to the query vector, filtered by disease label."""
        vector = query_vector.tolist() if isinstance(query_vector, np.ndarray) else query_vector

        results = self._client.query_points(
            collection_name=self.collection_name,
            query=vector,
            query_filter=Filter(
                must=[
                    FieldCondition(key="disease_label", match=MatchValue(value=disease_label)),
                ]
            ),
            limit=top_k,
            score_threshold=score_threshold,
        ).points
        return results

    def update_matched_queries(self, point_id: str, queries: list[dict]) -> None:
        """Update the matched_queries payload field for an existing point."""
        self._client.set_payload(
            collection_name=self.collection_name,
            payload={"matched_queries": queries},
            points=[point_id],
        )

    def count(self, source: str | None = None) -> int:
        count_filter = None
        if source:
            count_filter = Filter(
                must=[FieldCondition(key="source", match=MatchValue(value=source))]
            )
        result = self._client.count(
            collection_name=self.collection_name,
            count_filter=count_filter,
        )
        return result.count

    def get_collection_info(self) -> dict:
        info = self._client.get_collection(self.collection_name)
        return {
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
            "vector_size": info.config.params.vectors.size if info.config.params.vectors else None,
        }

    def close(self) -> None:
        self._client.close()
