"""Knowledge base schema definitions."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class KnowledgeBaseBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    enable_local: bool = True
    enable_naive_rag: bool = True
    enable_bm25: bool = False


class KnowledgeBaseCreate(KnowledgeBaseBase):
    pass


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    enable_local: Optional[bool] = None
    enable_naive_rag: Optional[bool] = None
    enable_bm25: Optional[bool] = None


class KnowledgeBase(KnowledgeBaseBase):
    id: int
    owner_id: int
    document_count: int
    total_chunks: int
    is_initialized: bool
    created_at: datetime
    updated_at: datetime
    entity_count: int = 0

    class Config:
        from_attributes = True
