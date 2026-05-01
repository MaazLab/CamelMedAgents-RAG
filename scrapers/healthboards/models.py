from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class Board(BaseModel):
    id: int
    name: str
    slug: str


class ThreadSummary(BaseModel):
    thread_id: int
    title: str = ""
    author: str = ""
    reply_count: int = 0
    view_count: int = 0
    last_post_date: str = ""


class ThreadPost(BaseModel):
    post_id: int
    post_number: int = 1
    author: str = ""
    post_date: str = ""
    html_content: str = ""
    reply_to_post_number: Optional[int] = None


class ThreadPage(BaseModel):
    thread_id: int
    title: str = ""
    page_number: int = 1
    total_pages: int = 1
    posts: list[ThreadPost] = Field(default_factory=list)
