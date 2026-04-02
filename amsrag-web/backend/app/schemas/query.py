"""Query request/response schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class HistoryMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = Field(..., min_length=1)


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    knowledge_base_id: int
    session_id: Optional[int] = Field(default=None, ge=1)
    mode: str = Field(
        default="naive",
        pattern="^(auto|naive|local|global|global_local|mix|bm25|llm_only)$",
    )
    top_k: int = Field(default=20, ge=1, le=100)
    use_memory: bool = True
    memory_turn_window: int = Field(default=4, ge=0, le=20)
    history_messages: List[HistoryMessage] = Field(default_factory=list)
    llm_provider: Optional[str] = Field(default=None, description="LLM provider override (dashscope, openai, deepseek, etc.)")
    llm_model: Optional[str] = Field(default=None, description="LLM model name override")


class QueryResponse(BaseModel):
    answer: str
    mode: str
    session_id: Optional[int] = None
    requested_mode: Optional[str] = None
    query_time: Optional[float] = None
    response_time: Optional[float] = None
    total_tokens: Optional[int] = None
    sources: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None


class QueryHistoryItem(BaseModel):
    id: int
    query: str
    question: str
    answer: str
    mode: Optional[str] = None
    kb_id: int
    knowledge_base_id: int
    kb_name: Optional[str] = None
    knowledge_base_name: Optional[str] = None
    duration: int = 0
    query_time: float = 0.0
    response_time: float = 0.0
    total_tokens: int = 0
    token_count: int = 0
    created_at: datetime
