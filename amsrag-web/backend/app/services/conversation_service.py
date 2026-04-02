"""Conversation session helpers."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.conversation import ConversationSession, ConversationTurn


def _normalize_session_title(question: str) -> str:
    title = " ".join((question or "").split()).strip()
    if not title:
        return "New conversation"
    return title[:80]


def get_or_create_conversation_session(
    db: Session,
    user_id: int,
    knowledge_base_id: int,
    session_id: int | None,
    title_source: str,
) -> Tuple[ConversationSession, bool]:
    if session_id is not None:
        session = (
            db.query(ConversationSession)
            .filter(
                ConversationSession.id == session_id,
                ConversationSession.user_id == user_id,
                ConversationSession.knowledge_base_id == knowledge_base_id,
            )
            .first()
        )
        if not session:
            raise LookupError("Conversation session not found.")
        return session, False

    session = ConversationSession(
        user_id=user_id,
        knowledge_base_id=knowledge_base_id,
        title=_normalize_session_title(title_source),
        last_active_at=datetime.utcnow(),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session, True


def get_recent_history_messages(
    db: Session,
    session_id: int,
    turn_window: int,
) -> List[Dict[str, str]]:
    if turn_window <= 0:
        return []

    turns = (
        db.query(ConversationTurn)
        .filter(ConversationTurn.session_id == session_id)
        .order_by(ConversationTurn.turn_index.desc())
        .limit(turn_window)
        .all()
    )

    messages: List[Dict[str, str]] = []
    for turn in reversed(turns):
        if turn.question:
            messages.append({"role": "user", "content": turn.question})
        if turn.answer:
            messages.append({"role": "assistant", "content": turn.answer})
    return messages


def list_conversation_sessions(
    db: Session,
    user_id: int,
    knowledge_base_id: int | None = None,
    skip: int = 0,
    limit: int = 50,
) -> List[ConversationSession]:
    query = db.query(ConversationSession).filter(ConversationSession.user_id == user_id)
    if knowledge_base_id is not None:
        query = query.filter(
            ConversationSession.knowledge_base_id == knowledge_base_id,
        )
    return (
        query.order_by(ConversationSession.last_active_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_conversation_session_detail(
    db: Session,
    user_id: int,
    session_id: int,
    knowledge_base_id: int | None = None,
) -> ConversationSession | None:
    query = db.query(ConversationSession).filter(
        ConversationSession.id == session_id,
        ConversationSession.user_id == user_id,
    )
    if knowledge_base_id is not None:
        query = query.filter(
            ConversationSession.knowledge_base_id == knowledge_base_id,
    )
    return query.first()


def delete_conversation_session(
    db: Session,
    user_id: int,
    session_id: int,
    knowledge_base_id: int | None = None,
) -> bool:
    session = get_conversation_session_detail(
        db=db,
        user_id=user_id,
        session_id=session_id,
        knowledge_base_id=knowledge_base_id,
    )
    if not session:
        return False

    db.delete(session)
    db.commit()
    return True


def save_conversation_turn(
    db: Session,
    session: ConversationSession,
    question: str,
    result: Dict[str, Any],
) -> ConversationTurn:
    max_turn_index = (
        db.query(func.max(ConversationTurn.turn_index))
        .filter(ConversationTurn.session_id == session.id)
        .scalar()
    )
    next_turn_index = (max_turn_index or 0) + 1

    if not session.title or session.title == "New conversation":
        session.title = _normalize_session_title(question)

    session.last_active_at = datetime.utcnow()

    turn = ConversationTurn(
        session_id=session.id,
        turn_index=next_turn_index,
        question=question,
        answer=result.get("answer", ""),
        requested_mode=result.get("requested_mode"),
        mode=result.get("mode"),
        response_time=result.get("response_time"),
        token_count=result.get("total_tokens"),
        sources_json=json.dumps(result.get("sources", []), ensure_ascii=False),
        memory_json=json.dumps(
            result.get("metadata", {}).get("memory", {}),
            ensure_ascii=False,
        ),
    )
    db.add(turn)
    db.add(session)
    db.commit()
    db.refresh(turn)
    return turn
