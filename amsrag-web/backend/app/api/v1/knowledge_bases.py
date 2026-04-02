"""Knowledge base management API."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.document import Document, DocumentStatus
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.schemas.knowledge_base import KnowledgeBase as KBSchema
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseUpdate
from app.core.config import settings
from app.services.rag_service import clear_rag_service_cache, get_initialized_rag_service
from app.services.runtime_service import cleanup_kb_runtime, detect_graph_source, get_provider_keys, rebuild_kb_runtime

router = APIRouter()


def _get_owned_kb(db: Session, user_id: int, kb_id: int) -> KnowledgeBase | None:
    return (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == user_id)
        .first()
    )


@router.get("/", response_model=List[KBSchema])
async def list_knowledge_bases(skip: int = 0, limit: int = 100, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kbs = db.query(KnowledgeBase).filter(KnowledgeBase.owner_id == current_user.id).offset(skip).limit(limit).all()
    return [
        {
            "id": kb.id,
            "name": kb.name,
            "description": kb.description,
            "owner_id": kb.owner_id,
            "enable_local": kb.enable_local,
            "enable_naive_rag": kb.enable_naive_rag,
            "enable_bm25": kb.enable_bm25,
            "document_count": kb.document_count,
            "total_chunks": kb.total_chunks,
            "is_initialized": kb.is_initialized,
            "created_at": kb.created_at,
            "updated_at": kb.updated_at,
            "entity_count": 0,
        }
        for kb in kbs
    ]


@router.post("/", response_model=KBSchema, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(kb_in: KnowledgeBaseCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kb = KnowledgeBase(
        name=kb_in.name,
        description=kb_in.description,
        owner_id=current_user.id,
        enable_local=kb_in.enable_local,
        enable_naive_rag=kb_in.enable_naive_rag,
        enable_bm25=kb_in.enable_bm25,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb


@router.get("/{kb_id}", response_model=KBSchema)
async def get_knowledge_base(kb_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kb = _get_owned_kb(db, current_user.id, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found.")
    return kb


@router.put("/{kb_id}", response_model=KBSchema)
async def update_knowledge_base(kb_id: int, kb_in: KnowledgeBaseUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kb = _get_owned_kb(db, current_user.id, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found.")
    update_data = kb_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(kb, field, value)
    db.commit()
    db.refresh(kb)
    clear_rag_service_cache(current_user.id, kb_id)
    return kb


@router.post("/{kb_id}/rebuild")
async def rebuild_knowledge_base(kb_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kb = _get_owned_kb(db, current_user.id, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found.")

    documents = db.query(Document).filter(Document.knowledge_base_id == kb.id).all()
    for document in documents:
        document.status = DocumentStatus.PROCESSING
        document.error_message = None
    kb.is_initialized = False
    db.commit()

    try:
        stats = await rebuild_kb_runtime(db, current_user, kb, documents)
        return {"message": "Knowledge base rebuilt successfully.", **stats}
    except Exception as exc:
        for document in documents:
            document.status = DocumentStatus.FAILED
            document.error_message = f"{exc.__class__.__name__}: {exc}"[:500]
        kb.is_initialized = False
        kb.total_chunks = 0
        db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to rebuild knowledge base: {exc}") from exc


@router.post("/{kb_id}/cleanup")
async def cleanup_knowledge_base(kb_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kb = _get_owned_kb(db, current_user.id, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found.")

    report = await cleanup_kb_runtime(current_user.id, kb.id)
    documents = db.query(Document).filter(Document.knowledge_base_id == kb.id).all()
    for document in documents:
        document.status = DocumentStatus.PENDING
        document.error_message = "Knowledge base runtime has been cleaned. Rebuild is required."
        document.chunk_count = 0
        document.processed_at = None
    kb.document_count = len(documents)
    kb.total_chunks = 0
    kb.is_initialized = False
    db.commit()
    return {"message": "Knowledge base runtime cleaned.", **report}


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(kb_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kb = _get_owned_kb(db, current_user.id, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found.")
    await cleanup_kb_runtime(current_user.id, kb_id)
    clear_rag_service_cache(current_user.id, kb_id)
    db.delete(kb)
    db.commit()
    return None


@router.get("/{kb_id}/statistics")
@router.get("/{kb_id}/stats")
async def get_kb_statistics(kb_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kb = _get_owned_kb(db, current_user.id, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found.")

    base_stats = {
        "initialized": kb.is_initialized,
        "document_count": kb.document_count,
        "total_chunks": kb.total_chunks,
        "entity_count": 0,
        "relation_count": 0,
        "chunks": 0,
        "graph_source": "none",
        "graph_backend_status": "error",
        "fallback_reason": "not_initialized" if not kb.is_initialized else None,
        "last_error": None,
    }

    if not kb.is_initialized:
        return base_stats

    llm_provider, llm_api_key, embedding_api_key = get_provider_keys(db, current_user.id)
    if not llm_provider or not llm_api_key or not embedding_api_key:
        base_stats.update({
            "graph_source": "none",
            "graph_backend_status": "error",
            "fallback_reason": "missing_provider_keys",
            "last_error": "缺少必要的密钥：请先配置 LLM 密钥和嵌入密钥。",
        })
        return base_stats

    try:
        rag_service = await get_initialized_rag_service(
            user_id=current_user.id,
            kb_id=kb_id,
            dashscope_key=llm_api_key,
            siliconflow_key=embedding_api_key,
            enable_local=kb.enable_local,
            enable_naive_rag=kb.enable_naive_rag,
            enable_bm25=kb.enable_bm25,
            llm_provider=llm_provider,
            llm_api_key=llm_api_key,
        )
        stats = rag_service.get_statistics()
        source_meta = detect_graph_source(current_user.id, kb.id, stats)
        return {
            "initialized": True,
            "document_count": kb.document_count,
            "total_chunks": kb.total_chunks,
            "entity_count": stats.get("nodes", 0),
            "relation_count": stats.get("edges", 0),
            "chunks": stats.get("chunks", 0),
            **source_meta,
        }
    except Exception as exc:
        base_stats.update({
            "graph_source": "none",
            "graph_backend_status": "error",
            "fallback_reason": "statistics_failed",
            "last_error": str(exc),
        })
        return base_stats


@router.get("/{kb_id}/graph")
async def get_kb_graph(kb_id: int, node_id: str | None = None, keyword: str | None = None, limit: int = 80, depth: int = 1, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kb = _get_owned_kb(db, current_user.id, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found.")
    if not kb.is_initialized:
        return {
            "nodes": [],
            "edges": [],
            "message": "Knowledge base is not initialized yet.",
            "source": "none",
            "graph_backend_status": "error",
            "fallback_reason": "not_initialized",
            "last_error": None,
        }

    llm_provider, llm_api_key, embedding_api_key = get_provider_keys(db, current_user.id)
    if not llm_provider or not llm_api_key or not embedding_api_key:
        return {
            "nodes": [],
            "edges": [],
            "message": "Missing provider API keys.",
            "source": "none",
            "graph_backend_status": "error",
            "fallback_reason": "missing_provider_keys",
            "last_error": "缺少必要的密钥：请先配置 LLM 密钥和嵌入密钥。",
        }

    try:
        rag_service = await get_initialized_rag_service(
            user_id=current_user.id,
            kb_id=kb_id,
            dashscope_key=llm_api_key,
            siliconflow_key=embedding_api_key,
            enable_local=kb.enable_local,
            enable_naive_rag=kb.enable_naive_rag,
            enable_bm25=kb.enable_bm25,
            llm_provider=llm_provider,
            llm_api_key=llm_api_key,
        )
        result = await rag_service.get_graph_data(node_id=node_id, keyword=keyword, limit=limit, depth=depth)
        if "source" not in result:
            if result.get("fallback") == "graphml":
                result["source"] = "graphml"
                result["graph_backend_status"] = "fallback"
            else:
                # rag_service 在 NetworkX / memory 分支下可能不会返回 source 字段。
                # 这里根据已请求的图后端来推断，避免在 networkx 模式下误标成 neo4j。
                if settings.RAG_GRAPH_BACKEND.strip().lower() != "neo4j":
                    result["source"] = "memory"
                    result["graph_backend_status"] = "ready"
                else:
                    result["source"] = "neo4j"
                    result["graph_backend_status"] = "ready"
        result.setdefault("fallback_reason", None)
        result.setdefault("last_error", None)
        return result
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch graph data: {exc}") from exc
