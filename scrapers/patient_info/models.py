from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class ForumCategory(BaseModel):
    id: int
    name: str
    slug: str
    topic_count: int = 0
    description: Optional[str] = None


class ForumTag(BaseModel):
    id: int
    name: str
    slug: str = ""
    count: int = Field(0, alias="topic_count")

    class Config:
        populate_by_name = True


class Post(BaseModel):
    id: int
    topic_id: int
    post_number: int
    username: str = ""
    cooked: str = ""  # raw HTML
    created_at: str = ""
    reply_to_post_number: Optional[int] = None
    post_type: int = 1
    score: float = 0.0
    word_count: Optional[int] = None


class TopicSummary(BaseModel):
    id: int
    title: str = ""
    slug: str = ""
    category_id: Optional[int] = None
    tags: list[str] = Field(default_factory=list)
    posts_count: int = 0
    views: int = 0
    created_at: str = ""
    last_posted_at: str = ""
    visible: bool = True


class PostStream(BaseModel):
    posts: list[Post] = Field(default_factory=list)
    stream: list[int] = Field(default_factory=list)


class TopicTag(BaseModel):
    id: int
    name: str
    slug: str = ""


class Topic(BaseModel):
    id: int
    title: str = ""
    slug: str = ""
    category_id: Optional[int] = None
    tags: list[TopicTag] = Field(default_factory=list)
    posts_count: int = 0
    views: int = 0
    created_at: str = ""
    last_posted_at: str = ""
    visible: bool = True
    word_count: Optional[int] = None
    post_stream: PostStream = Field(default_factory=PostStream)
