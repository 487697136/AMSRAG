from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import settings
from app.models.api_key import APIKey
from app.models.document import Document, DocumentStatus
from app.utils.crypto import decrypt_api_key
from app.services import rag_service as rag_service_module
from app.services.rag_service import get_initialized_rag_service

GRAPHML_FILENAME = "graph_chunk_entity_relation.graphml"


def get_workspace_path(user_id: int, kb_id: int) -> Path:
    return Path(settings.RAG_WORKSPACE_DIR) / f"user_{user_id}" / f"kb_{kb_id}"


def get_graphml_path(user_id: int, kb_id: int) -> Path:
    return get_workspace_path(user_id, kb_id) / GRAPHML_FILENAME


def compute_graph_namespace(user_id: int, kb_id: int) -> str | None:
    if settings.RAG_GRAPH_BACKEND.strip().lower() != "neo4j":
        return None
    try:
        from amsrag._storage.graph.neo4j import make_path_idable

        return f"{make_path_idable(str(get_workspace_path(user_id, kb_id)))}__chunk_entity_relation"
    except Exception:
        return None


def get_provider_keys(db, user_id: int) -> tuple[str | None, str | None, str | None, str]:
    """
    Resolve keys from user's configured API keys.

    Returns:
      (llm_provider, llm_api_key, embedding_api_key, embedding_model)
      embedding_model defaults to "BAAI/bge-m3" if not explicitly set.
    """
    from app.schemas.api_key import DEFAULT_EMBEDDING_MODEL

    all_keys = db.query(APIKey).filter(APIKey.user_id == user_id).all()
    key_map: dict = {}
    # 同时保存 model_name 字段
    model_map: dict = {}
    for k in all_keys:
        try:
            decrypted = decrypt_api_key(k.encrypted_key)
            if decrypted:
                key_map[k.provider] = decrypted
                if k.model_name:
                    model_map[k.provider] = k.model_name
        except Exception as _dec_err:
            logger.warning(f"Failed to decrypt API key for provider={k.provider}: {_dec_err}")

    # Embedding: currently the system uses SiliconFlow embedding.
    embedding_api_key = key_map.get("siliconflow")
    if not embedding_api_key:
        return None, None, None, ""

    # 读取用户为 siliconflow 设置的模型，默认 BAAI/bge-m3
    embedding_model = model_map.get("siliconflow") or DEFAULT_EMBEDDING_MODEL.get("siliconflow", "BAAI/bge-m3")

    # LLM: pick the first configured LLM provider (prefer dashscope).
    llm_candidates_prefer = ("dashscope", "openai", "deepseek", "zhipu", "moonshot", "openrouter")
    llm_provider = None
    for p in llm_candidates_prefer:
        if key_map.get(p):
            llm_provider = p
            break

    # If none of the preferred providers exists, fall back to any non-embedding provider.
    if not llm_provider:
        for p in key_map.keys():
            if p != "siliconflow" and key_map.get(p):
                llm_provider = p
                break

    if not llm_provider:
        return None, None, None, ""

    llm_api_key = key_map.get(llm_provider)
    if not llm_api_key:
        return None, None, None, ""

    return llm_provider, llm_api_key, embedding_api_key, embedding_model


async def close_cached_rag_service(user_id: int, kb_id: int) -> None:
    services = []
    async with rag_service_module._rag_service_cache_lock:
        for key in list(rag_service_module._rag_service_cache.keys()):
            if key[0] == user_id and key[1] == kb_id:
                services.append(rag_service_module._rag_service_cache.pop(key))

    for service in services:
        graph_storage = getattr(getattr(service, "rag_instance", None), "chunk_entity_relation_graph", None)
        close_method = getattr(graph_storage, "close", None)
        async_driver = getattr(graph_storage, "async_driver", None)
        try:
            if callable(close_method):
                result = close_method()
                if hasattr(result, "__await__"):
                    await result
            elif async_driver is not None:
                await async_driver.close()
        except Exception as exc:
            logger.debug("Failed to close cached RAG service for user={}, kb={}: {}", user_id, kb_id, exc)


async def cleanup_kb_runtime(user_id: int, kb_id: int) -> dict[str, Any]:
    await close_cached_rag_service(user_id, kb_id)

    report = {
        "user_id": user_id,
        "kb_id": kb_id,
        "workspace_removed": False,
        "neo4j_cleared": False,
        "graph_namespace": compute_graph_namespace(user_id, kb_id),
    }

    namespace = report["graph_namespace"]
    neo4j_auth = settings.get_neo4j_auth()
    if namespace and settings.NEO4J_URL and neo4j_auth:
        try:
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver(settings.NEO4J_URL, auth=neo4j_auth)
            try:
                with driver.session() as session:
                    session.run(f"MATCH (n:`{namespace}`)-[r]-() DELETE r").consume()
                    session.run(f"MATCH (n:`{namespace}`) DELETE n").consume()
                report["neo4j_cleared"] = True
            finally:
                driver.close()
        except Exception as exc:
            logger.warning("Failed to clear Neo4j runtime for user={}, kb={}: {}", user_id, kb_id, exc)
            report["last_error"] = str(exc)

    workspace_path = get_workspace_path(user_id, kb_id)
    if workspace_path.exists():
        import shutil

        shutil.rmtree(workspace_path, ignore_errors=True)
        report["workspace_removed"] = not workspace_path.exists()

    return report


def detect_graph_source(user_id: int, kb_id: int, stats: dict[str, Any] | None = None) -> dict[str, Any]:
    stats = stats or {}
    requested_backend = settings.RAG_GRAPH_BACKEND.strip().lower()
    graphml_exists = get_graphml_path(user_id, kb_id).exists()
    namespace = compute_graph_namespace(user_id, kb_id)
    neo4j_auth = settings.get_neo4j_auth()

    if not stats.get("initialized"):
        return {
            "graph_source": "none",
            "graph_backend_status": "error",
            "fallback_reason": "not_initialized",
            "last_error": stats.get("last_error"),
        }

    if requested_backend != "neo4j":
        return {
            "graph_source": "memory",
            "graph_backend_status": "ready",
            "fallback_reason": None,
            "last_error": stats.get("last_error"),
        }

    if namespace and settings.NEO4J_URL and neo4j_auth:
        try:
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver(settings.NEO4J_URL, auth=neo4j_auth)
            try:
                with driver.session() as session:
                    node_count = session.run(f"MATCH (n:`{namespace}`) RETURN count(n) AS c").single()["c"]
                if node_count > 0:
                    return {
                        "graph_source": "neo4j",
                        "graph_backend_status": "ready",
                        "fallback_reason": None,
                        "last_error": stats.get("last_error"),
                    }
            finally:
                driver.close()
        except Exception as exc:
            if graphml_exists and (stats.get("nodes") or stats.get("edges")):
                return {
                    "graph_source": "graphml",
                    "graph_backend_status": "fallback",
                    "fallback_reason": "neo4j_query_failed",
                    "last_error": str(exc),
                }
            return {
                "graph_source": "none",
                "graph_backend_status": "error",
                "fallback_reason": "neo4j_query_failed",
                "last_error": str(exc),
            }

    if graphml_exists and (stats.get("nodes") or stats.get("edges")):
        return {
            "graph_source": "graphml",
            "graph_backend_status": "fallback",
            "fallback_reason": "neo4j_unavailable",
            "last_error": stats.get("last_error"),
        }

    return {
        "graph_source": "neo4j",
        "graph_backend_status": "ready",
        "fallback_reason": None,
        "last_error": stats.get("last_error"),
    }

async def rebuild_kb_runtime(db, current_user, kb, documents: list[Document] | None = None) -> dict[str, Any]:
    llm_provider, llm_api_key, embedding_api_key, embedding_model = get_provider_keys(db, current_user.id)
    if not llm_provider or not llm_api_key or not embedding_api_key:
        raise RuntimeError("缺少必要的密钥：请先配置一个可用的 LLM 密钥和一个嵌入密钥。")

    candidate_documents = documents or (
        db.query(Document)
        .filter(Document.knowledge_base_id == kb.id)
        .order_by(Document.created_at.asc(), Document.id.asc())
        .all()
    )

    await cleanup_kb_runtime(current_user.id, kb.id)

    if not candidate_documents:
        kb.document_count = 0
        kb.total_chunks = 0
        kb.is_initialized = False
        db.commit()
        return {
            "initialized": False,
            "nodes": 0,
            "edges": 0,
            "chunks": 0,
            "graph_source": "none",
            "graph_backend_status": "error",
            "fallback_reason": "empty_knowledge_base",
            "last_error": None,
            "processed_documents": [],
        }

    rag_service = await get_initialized_rag_service(
        user_id=current_user.id,
        kb_id=kb.id,
        dashscope_key=llm_api_key,
        siliconflow_key=embedding_api_key,
        enable_local=kb.enable_local,
        enable_naive_rag=kb.enable_naive_rag,
        enable_bm25=kb.enable_bm25,
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
        embedding_model=embedding_model,
    )

    processed_documents = []
    total_chunks = 0
    completed_documents = 0
    now = datetime.utcnow()

    try:
        for document in candidate_documents:
            content = str(document.content or "").strip()
            if not content:
                document.status = DocumentStatus.FAILED
                document.error_message = "Document content is empty."
                document.chunk_count = 0
                processed_documents.append(
                    {"id": document.id, "chunk_count": 0, "status": DocumentStatus.FAILED.value}
                )
                continue

            before_chunks = int(rag_service.get_statistics().get("chunks", 0))
            await rag_service.insert_document(content)
            after_chunks = int(rag_service.get_statistics().get("chunks", before_chunks))
            chunk_count = max(0, after_chunks - before_chunks)

            document.status = DocumentStatus.COMPLETED
            document.error_message = None
            document.chunk_count = chunk_count
            document.processed_at = now
            processed_documents.append(
                {"id": document.id, "chunk_count": chunk_count, "status": DocumentStatus.COMPLETED.value}
            )
            total_chunks += chunk_count
            completed_documents += 1

        kb.document_count = len(candidate_documents)
        kb.total_chunks = total_chunks
        kb.is_initialized = completed_documents > 0
        db.commit()

        stats = rag_service.get_statistics()
        stats.update(detect_graph_source(current_user.id, kb.id, stats))
        stats["processed_documents"] = processed_documents
        return stats
    except Exception:
        db.rollback()
        await cleanup_kb_runtime(current_user.id, kb.id)
        raise
