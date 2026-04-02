"""Short-term conversation memory helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.conversation import ConversationTurn

SUMMARY_MAX_TURNS = 8
SUMMARY_CHAR_LIMIT = 1200
QUESTION_SNIPPET_LIMIT = 120
ANSWER_SNIPPET_LIMIT = 220

_summary_cache: Dict[tuple[int, int, int], str] = {}


def _normalize_text(text: str | None) -> str:
    return " ".join((text or "").split()).strip()


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 3, 0)].rstrip()}..."


def _serialize_turn_messages(turns: List[ConversationTurn]) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    for turn in turns:
        question = _normalize_text(turn.question)
        answer = _normalize_text(turn.answer)
        if question:
            messages.append({"role": "user", "content": question})
        if answer:
            messages.append({"role": "assistant", "content": answer})
    return messages


def _build_summary_message(
    turns: List[ConversationTurn],
    skipped_turns: int = 0,
) -> str:
    if not turns:
        return ""

    lines = [
        "Conversation summary from earlier turns.",
        f"Earlier turns retained in summary: {len(turns)}.",
    ]
    if skipped_turns:
        lines.append(
            f"Older summarized turns omitted from detail: {skipped_turns}."
        )

    for turn in turns:
        question = _truncate_text(_normalize_text(turn.question), QUESTION_SNIPPET_LIMIT)
        answer = _truncate_text(_normalize_text(turn.answer), ANSWER_SNIPPET_LIMIT)
        if answer:
            lines.append(
                f"Turn {turn.turn_index}: user asked '{question}'; assistant answered '{answer}'."
            )
        else:
            lines.append(
                f"Turn {turn.turn_index}: user asked '{question}'."
            )

    summary = "\n".join(lines)
    return _truncate_text(summary, SUMMARY_CHAR_LIMIT)


def build_session_memory_messages(
    db: Session,
    session_id: int,
    turn_window: int,
) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    if turn_window <= 0:
        return [], {
            "used": False,
            "strategy": "disabled",
            "recent_turn_count": 0,
            "summary_used": False,
            "summary_turn_count": 0,
        }

    total_turns = (
        db.query(func.count(ConversationTurn.id))
        .filter(ConversationTurn.session_id == session_id)
        .scalar()
        or 0
    )
    if total_turns <= 0:
        return [], {
            "used": False,
            "strategy": "empty_session",
            "recent_turn_count": 0,
            "summary_used": False,
            "summary_turn_count": 0,
        }

    recent_turns = (
        db.query(ConversationTurn)
        .filter(ConversationTurn.session_id == session_id)
        .order_by(ConversationTurn.turn_index.desc())
        .limit(turn_window)
        .all()
    )
    recent_turns.reverse()

    older_turn_count = max(total_turns - len(recent_turns), 0)
    summary_turns: List[ConversationTurn] = []
    skipped_turns = 0
    summary_message = ""
    if older_turn_count > 0:
        cache_key = (session_id, total_turns, turn_window)
        summary_message = _summary_cache.get(cache_key, "")
        if not summary_message:
            summary_turns = (
                db.query(ConversationTurn)
                .filter(ConversationTurn.session_id == session_id)
                .order_by(ConversationTurn.turn_index.desc())
                .offset(len(recent_turns))
                .limit(SUMMARY_MAX_TURNS)
                .all()
            )
            summary_turns.reverse()
            skipped_turns = max(older_turn_count - len(summary_turns), 0)
            summary_message = _build_summary_message(
                summary_turns,
                skipped_turns=skipped_turns,
            )
            _summary_cache[cache_key] = summary_message
        else:
            skipped_turns = max(older_turn_count - SUMMARY_MAX_TURNS, 0)

    messages: List[Dict[str, str]] = []
    if summary_message:
        messages.append({"role": "system", "content": summary_message})
    messages.extend(_serialize_turn_messages(recent_turns))

    return messages, {
        "used": bool(messages),
        "strategy": "window_with_summary" if older_turn_count else "window_only",
        "recent_turn_count": len(recent_turns),
        "summary_used": bool(summary_message),
        "summary_turn_count": older_turn_count,
        "message_count": len(messages),
    }
