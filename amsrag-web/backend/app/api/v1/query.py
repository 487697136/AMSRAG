"""Query API endpoints."""

import asyncio
import json
from typing import List, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.db.session import SessionLocal, get_db
from app.models.conversation import ConversationSession
from app.models.knowledge_base import KnowledgeBase
from app.models.query_history import QueryHistory
from app.models.user import User
from app.schemas.conversation import (
    ConversationSessionDetail,
    ConversationSessionSummary,
    ConversationTurnResponse,
)
from app.schemas.query import QueryHistoryItem, QueryRequest, QueryResponse
from app.services.conversation_service import (
    delete_conversation_session,
    get_conversation_session_detail,
    get_or_create_conversation_session,
    list_conversation_sessions,
    save_conversation_turn,
)
from app.services.memory_service import build_session_memory_messages
from app.services.rag_service import get_initialized_rag_service

router = APIRouter()


def _get_owned_kb(db: Session, user_id: int, kb_id: int) -> KnowledgeBase | None:
    return (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == user_id)
        .first()
    )


def _get_provider_keys(db: Session, user_id: int, llm_provider: str = "") -> Tuple[str, str, str, str, str]:
    """Return (dashscope_key, siliconflow_key, llm_provider, llm_api_key, embedding_model)."""
    from app.models.api_key import APIKey
    from app.schemas.api_key import DEFAULT_EMBEDDING_MODEL
    from app.utils.crypto import decrypt_api_key

    all_keys = db.query(APIKey).filter(APIKey.user_id == user_id).all()
    key_map: dict = {}
    embedding_model = ""
    for _k in all_keys:
        try:
            _dec = decrypt_api_key(_k.encrypted_key)
            if _dec:
                key_map[_k.provider] = _dec
                if _k.provider == "siliconflow" and _k.model_name:
                    embedding_model = _k.model_name
        except Exception as _dec_err:
            import warnings
            warnings.warn(f"Failed to decrypt key for provider={_k.provider}: {_dec_err}")

    if not embedding_model:
        embedding_model = DEFAULT_EMBEDDING_MODEL.get("siliconflow", "BAAI/bge-m3")

    siliconflow_key = key_map.get("siliconflow", "")
    if not siliconflow_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先在系统设置中配置 SiliconFlow（嵌入模型）API Key。",
        )

    resolved_llm_provider = llm_provider or ""
    resolved_llm_key = ""

    if resolved_llm_provider and resolved_llm_provider in key_map:
        resolved_llm_key = key_map[resolved_llm_provider]
    elif resolved_llm_provider and resolved_llm_provider not in key_map:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"所选 LLM 服务商 {resolved_llm_provider} 尚未配置 API Key，请先在系统设置中添加。",
        )

    dashscope_key = key_map.get("dashscope", "")
    if not dashscope_key and not resolved_llm_provider:
        has_any_llm = any(p in key_map for p in ("dashscope", "openai", "deepseek", "zhipu", "moonshot", "openrouter"))
        if not has_any_llm:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="请先在系统设置中配置至少一个 LLM 服务商的 API Key。",
            )
        for fallback_provider in ("openai", "deepseek", "zhipu", "moonshot", "openrouter"):
            if fallback_provider in key_map:
                resolved_llm_provider = fallback_provider
                resolved_llm_key = key_map[fallback_provider]
                break

    return (dashscope_key, siliconflow_key, resolved_llm_provider, resolved_llm_key, embedding_model)


async def _prepare_query_service(
    query_req: QueryRequest,
    current_user: User,
    db: Session,
):
    kb = _get_owned_kb(db, current_user.id, query_req.knowledge_base_id)
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )
    # llm_only mode does not require an initialized knowledge base
    if not kb.is_initialized and query_req.mode != "llm_only":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Knowledge base is not initialized yet. Please upload documents first, or switch to '仅模型回答' mode.",
        )

    dashscope_key, siliconflow_key, llm_provider, llm_api_key, embedding_model = _get_provider_keys(
        db, current_user.id, getattr(query_req, "llm_provider", "") or ""
    )
    rag_service = await get_initialized_rag_service(
        user_id=current_user.id,
        kb_id=query_req.knowledge_base_id,
        dashscope_key=dashscope_key,
        siliconflow_key=siliconflow_key,
        enable_local=kb.enable_local,
        enable_naive_rag=kb.enable_naive_rag,
        enable_bm25=kb.enable_bm25,
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
        llm_model=getattr(query_req, "llm_model", "") or "",
        embedding_model=embedding_model,
    )
    return kb, rag_service


def _save_query_history(
    db: Session,
    current_user: User,
    query_req: QueryRequest,
    result: dict,
) -> None:
    history = QueryHistory(
        question=query_req.question,
        answer=result["answer"],
        mode=result["mode"],
        user_id=current_user.id,
        knowledge_base_id=query_req.knowledge_base_id,
        response_time=result.get("response_time") or 0.0,
        token_count=result.get("total_tokens"),
    )
    db.add(history)
    db.commit()


def _resolve_history_messages(
    db: Session,
    query_req: QueryRequest,
    session_id: int,
) -> tuple[list[dict], dict]:
    if not query_req.use_memory:
        return [], {
            "source": "disabled",
            "used": False,
            "strategy": "disabled",
            "recent_turn_count": 0,
            "summary_used": False,
            "summary_turn_count": 0,
            "message_count": 0,
        }

    server_history, server_memory_meta = build_session_memory_messages(
        db,
        session_id=session_id,
        turn_window=query_req.memory_turn_window,
    )
    request_history = [message.model_dump() for message in query_req.history_messages]

    if server_history:
        return server_history, {
            **server_memory_meta,
            "source": "server_session",
        }

    if request_history:
        return request_history, {
            "source": "request_payload",
            "used": True,
            "strategy": "request_payload",
            "recent_turn_count": min(
                len(request_history) // 2,
                query_req.memory_turn_window,
            ),
            "summary_used": False,
            "summary_turn_count": 0,
            "message_count": len(request_history),
        }

    return [], {
        **server_memory_meta,
        "source": "none",
    }



def _split_stream_chunks(text: str, chunk_size: int = 24) -> List[str]:
    if not text:
        return [""]
    return [text[index : index + chunk_size] for index in range(0, len(text), chunk_size)]


def _serialize_session_summary(session) -> ConversationSessionSummary:
    return ConversationSessionSummary(
        id=session.id,
        title=session.title,
        knowledge_base_id=session.knowledge_base_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        last_active_at=session.last_active_at,
        turn_count=len(session.turns),
    )


def _serialize_query_history_item(history: QueryHistory) -> QueryHistoryItem:
    kb_name = (
        history.knowledge_base.name
        if history.knowledge_base is not None
        else None
    )
    response_time = float(history.response_time or 0.0)
    token_count = int(history.token_count or 0)

    return QueryHistoryItem(
        id=history.id,
        query=history.question,
        question=history.question,
        answer=history.answer or "",
        mode=history.mode,
        kb_id=history.knowledge_base_id,
        knowledge_base_id=history.knowledge_base_id,
        kb_name=kb_name,
        knowledge_base_name=kb_name,
        duration=int(response_time * 1000),
        query_time=response_time,
        response_time=response_time,
        total_tokens=token_count,
        token_count=token_count,
        created_at=history.created_at,
    )


@router.post("/", response_model=QueryResponse)
async def execute_query(
    query_req: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        _, rag_service = await _prepare_query_service(query_req, current_user, db)
        # Hard guarantee: llm_only should not use any conversation memory.
        # This avoids "KB content leakage" via assistant turns from previous modes.
        if query_req.mode == "llm_only":
            query_req.use_memory = False
            query_req.memory_turn_window = 0
        conversation_session, _ = get_or_create_conversation_session(
            db=db,
            user_id=current_user.id,
            knowledge_base_id=query_req.knowledge_base_id,
            session_id=query_req.session_id,
            title_source=query_req.question,
        )
        history_messages, memory_meta = _resolve_history_messages(
            db=db,
            query_req=query_req,
            session_id=conversation_session.id,
        )
        if query_req.mode == "llm_only":
            # Explicitly mark memory as forced off for clients/diagnostics.
            memory_meta = {**memory_meta, "llm_only_memory_forced_off": True}
        result = await rag_service.query_with_details(
            query_req.question,
            query_req.mode,
            query_req.top_k,
            history_messages=history_messages,
            use_memory=query_req.use_memory,
            memory_turn_window=query_req.memory_turn_window,
        )
        result["session_id"] = conversation_session.id
        result.setdefault("metadata", {})["memory"] = {
            **result.setdefault("metadata", {}).get("memory", {}),
            **memory_meta,
        }
        save_conversation_turn(
            db=db,
            session=conversation_session,
            question=query_req.question,
            result=result,
        )
        _save_query_history(db, current_user, query_req, result)
        return QueryResponse(**result)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query failed: {exc}",
        ) from exc


@router.post("/stream")
async def execute_query_stream(
    query_req: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        _, rag_service = await _prepare_query_service(query_req, current_user, db)
        # Hard guarantee: llm_only should not use any conversation memory.
        if query_req.mode == "llm_only":
            query_req.use_memory = False
            query_req.memory_turn_window = 0
        conversation_session, _ = get_or_create_conversation_session(
            db=db,
            user_id=current_user.id,
            knowledge_base_id=query_req.knowledge_base_id,
            session_id=query_req.session_id,
            title_source=query_req.question,
        )
        history_messages, memory_meta = _resolve_history_messages(
            db=db,
            query_req=query_req,
            session_id=conversation_session.id,
        )
        if query_req.mode == "llm_only":
            memory_meta = {**memory_meta, "llm_only_memory_forced_off": True}
        # Capture plain IDs before the request's DB session is closed.
        # The query_worker runs inside an asyncio task AFTER the streaming
        # response starts, at which point FastAPI has already closed `db` and
        # detached all ORM objects bound to it (including current_user).
        captured_user_id: int = current_user.id
        captured_session_id: int = conversation_session.id
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query failed: {exc}",
        ) from exc

    event_queue: asyncio.Queue[dict] = asyncio.Queue()

    async def handle_stream_chunk(content: str) -> None:
        if content:
            await event_queue.put({"type": "content", "content": content})

    async def query_worker() -> None:
        try:
            result = await rag_service.query_with_details(
                query_req.question,
                query_req.mode,
                query_req.top_k,
                history_messages=history_messages,
                use_memory=query_req.use_memory,
                memory_turn_window=query_req.memory_turn_window,
                stream_callback=handle_stream_chunk,
            )
            result["session_id"] = captured_session_id
            result.setdefault("metadata", {})["memory"] = {
                **result.setdefault("metadata", {}).get("memory", {}),
                **memory_meta,
            }
            # Open a fresh DB session: the request-scoped `db` is already
            # closed by the time this background task runs, which causes
            # "Instance not bound to a Session" errors on any ORM object access.
            worker_db = SessionLocal()
            try:
                worker_session = worker_db.get(ConversationSession, captured_session_id)
                if worker_session:
                    save_conversation_turn(
                        db=worker_db,
                        session=worker_session,
                        question=query_req.question,
                        result=result,
                    )
                history_entry = QueryHistory(
                    question=query_req.question,
                    answer=result.get("answer", ""),
                    mode=result.get("mode", query_req.mode),
                    user_id=captured_user_id,
                    knowledge_base_id=query_req.knowledge_base_id,
                    response_time=float(result.get("query_time") or 0.0),
                    token_count=result.get("total_tokens"),
                )
                worker_db.add(history_entry)
                worker_db.commit()
            except Exception as db_exc:
                worker_db.rollback()
                raise db_exc
            finally:
                worker_db.close()

            await event_queue.put(
                {
                    "type": "done",
                    "payload": {
                        "done": True,
                        "tokens": result.get("total_tokens", 0),
                        "mode": result.get("mode"),
                        "session_id": result.get("session_id"),
                        "query_time": result.get("query_time"),
                        "metadata": result.get("metadata"),
                        "sources": result.get("sources"),
                        "answer": result.get("answer", ""),
                    },
                }
            )
        except HTTPException as exc:
            await event_queue.put(
                {
                    "type": "error",
                    "payload": {
                        "done": True,
                        "error": exc.detail,
                        "status_code": exc.status_code,
                    },
                }
            )
        except Exception as exc:
            await event_queue.put(
                {
                    "type": "error",
                    "payload": {
                        "done": True,
                        "error": f"Query failed: {exc}",
                        "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    },
                }
            )
        finally:
            await event_queue.put({"type": "close"})

    async def event_stream():
        worker = asyncio.create_task(query_worker())
        try:
            while True:
                event = await event_queue.get()
                event_type = event.get("type")
                if event_type == "close":
                    break
                if event_type == "content":
                    yield f"data: {json.dumps({'content': event.get('content', '')}, ensure_ascii=False)}\n\n"
                    continue
                if event_type in {"done", "error"}:
                    yield f"data: {json.dumps(event.get('payload', {}), ensure_ascii=False)}\n\n"
        finally:
            await worker

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history", response_model=list[QueryHistoryItem])
async def get_query_history(
    kb_id: int = None,
    mode: str = None,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = (
        db.query(QueryHistory)
        .options(joinedload(QueryHistory.knowledge_base))
        .filter(QueryHistory.user_id == current_user.id)
    )

    if kb_id:
        query = query.filter(QueryHistory.knowledge_base_id == kb_id)
    if mode:
        query = query.filter(QueryHistory.mode == mode)

    histories = (
        query.order_by(QueryHistory.created_at.desc()).offset(skip).limit(limit).all()
    )
    return [_serialize_query_history_item(item) for item in histories]


@router.delete("/history/all")
@router.delete("/history")
async def clear_query_history(
    kb_id: int = None,
    mode: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(QueryHistory).filter(QueryHistory.user_id == current_user.id)
    if kb_id:
        query = query.filter(QueryHistory.knowledge_base_id == kb_id)
    if mode:
        query = query.filter(QueryHistory.mode == mode)

    deleted_count = query.delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted_count}


@router.delete("/history/{history_id}")
async def delete_query_history_item(
    history_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    history_item = (
        db.query(QueryHistory)
        .filter(
            QueryHistory.id == history_id,
            QueryHistory.user_id == current_user.id,
        )
        .first()
    )
    if not history_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Query history not found.",
        )

    db.delete(history_item)
    db.commit()
    return {"deleted": True, "id": history_id}


@router.get("/sessions", response_model=list[ConversationSessionSummary])
async def get_conversation_sessions(
    kb_id: int = None,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sessions = list_conversation_sessions(
        db=db,
        user_id=current_user.id,
        knowledge_base_id=kb_id,
        skip=skip,
        limit=limit,
    )
    return [_serialize_session_summary(session) for session in sessions]


@router.get("/sessions/{session_id}", response_model=ConversationSessionDetail)
async def get_conversation_session_detail_api(
    session_id: int,
    kb_id: int = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = get_conversation_session_detail(
        db=db,
        user_id=current_user.id,
        session_id=session_id,
        knowledge_base_id=kb_id,
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation session not found.",
        )

    def _safe_json_loads(raw: str | None, default):
        if not raw:
            return default
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return default

    turns = [
        ConversationTurnResponse(
            id=turn.id,
            turn_index=turn.turn_index,
            question=turn.question,
            answer=turn.answer,
            requested_mode=turn.requested_mode,
            mode=turn.mode,
            response_time=turn.response_time,
            token_count=turn.token_count,
            sources=_safe_json_loads(turn.sources_json, []),
            memory=_safe_json_loads(turn.memory_json, {}),
            created_at=turn.created_at,
        )
        for turn in session.turns
    ]
    return ConversationSessionDetail(
        session=_serialize_session_summary(session),
        turns=turns,
    )


@router.delete("/sessions/{session_id}")
async def delete_conversation_session_api(
    session_id: int,
    kb_id: int = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    deleted = delete_conversation_session(
        db=db,
        user_id=current_user.id,
        session_id=session_id,
        knowledge_base_id=kb_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation session not found.",
        )
    return {"deleted": True, "session_id": session_id}
