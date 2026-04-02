"""Conversation schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ConversationSessionSummary(BaseModel):
    id: int
    title: str
    knowledge_base_id: int
    created_at: datetime
    updated_at: datetime
    last_active_at: datetime
    turn_count: int


class ConversationTurnResponse(BaseModel):
    id: int
    turn_index: int
    question: str
    answer: Optional[str] = None
    requested_mode: Optional[str] = None
    mode: Optional[str] = None
    response_time: Optional[float] = None
    token_count: Optional[int] = None
    sources: Optional[List[Dict[str, Any]]] = None
    memory: Optional[Dict[str, Any]] = None
    created_at: datetime


class ConversationSessionDetail(BaseModel):
    session: ConversationSessionSummary
    turns: List[ConversationTurnResponse]
