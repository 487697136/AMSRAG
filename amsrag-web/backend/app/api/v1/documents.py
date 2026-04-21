"""Document APIs."""

from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.models.document import Document, DocumentStatus
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.schemas.document import Document as DocSchema
from app.services.rag_service import get_initialized_rag_service
from app.services.runtime_service import cleanup_kb_runtime, get_provider_keys, rebuild_kb_runtime

router = APIRouter()


def _get_owned_kb(db: Session, user_id: int, kb_id: int) -> KnowledgeBase | None:
    return (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == user_id)
        .first()
    )


def _get_owned_document(db: Session, user_id: int, doc_id: int) -> tuple[Document | None, KnowledgeBase | None]:
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        return None, None
    kb = _get_owned_kb(db, user_id, doc.knowledge_base_id)
    return doc, kb


@router.get("/", response_model=List[DocSchema])
async def list_documents(
    kb_id: int,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kb = _get_owned_kb(db, current_user.id, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    return db.query(Document).filter(Document.knowledge_base_id == kb_id).offset(skip).limit(limit).all()


async def process_document_background(doc_id: int, user_id: int, kb_id: int, text_content: str):
    from app.core.logging import logger

    db = SessionLocal()
    doc = None
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
        user = db.query(User).filter(User.id == user_id).first()
        if not doc or not kb or not user:
            logger.error("Document processing aborted: missing doc/kb/user doc_id={} kb_id={} user_id={}", doc_id, kb_id, user_id)
            return

        doc.status = DocumentStatus.PROCESSING
        doc.progress = 0
        doc.progress_stage = "准备就绪"
        doc.error_message = None
        db.commit()

        llm_provider, llm_api_key, embedding_api_key, embedding_model = get_provider_keys(db, user_id)
        if not llm_provider or not llm_api_key or not embedding_api_key:
            raise RuntimeError("缺少必要的密钥：请先配置一个可用的 LLM 密钥和一个嵌入密钥。")

        rag_service = await get_initialized_rag_service(
            user_id=user_id,
            kb_id=kb_id,
            dashscope_key=llm_api_key,
            siliconflow_key=embedding_api_key,
            enable_local=kb.enable_local,
            enable_naive_rag=kb.enable_naive_rag,
            enable_bm25=kb.enable_bm25,
            llm_provider=llm_provider,
            llm_api_key=llm_api_key,
            embedding_model=embedding_model,
        )

        def _on_progress(pct: int, stage: str) -> None:
            """同步进度回调：更新数据库中的文档进度字段。"""
            try:
                _progress_db = SessionLocal()
                try:
                    _doc = _progress_db.query(Document).filter(Document.id == doc_id).first()
                    if _doc:
                        _doc.progress = pct
                        _doc.progress_stage = stage
                        _progress_db.commit()
                finally:
                    _progress_db.close()
            except Exception as _e:
                logger.warning(f"Failed to update document progress: {_e}")

        before_chunks = int(rag_service.get_statistics().get("chunks", 0))
        stats = await rag_service.insert_document(text_content, progress_callback=_on_progress)
        after_chunks = int(stats.get("chunks", before_chunks))

        doc.status = DocumentStatus.COMPLETED
        doc.error_message = None
        doc.processed_at = datetime.utcnow()
        doc.chunk_count = max(0, after_chunks - before_chunks)

        kb.document_count = db.query(Document).filter(Document.knowledge_base_id == kb_id).count()
        kb.total_chunks = int(stats.get("chunks", kb.total_chunks + doc.chunk_count))
        kb.is_initialized = True
        db.commit()
    except Exception as exc:
        if doc:
            doc.status = DocumentStatus.FAILED
            doc.error_message = f"{exc.__class__.__name__}: {exc}"[:500]
            db.commit()
    finally:
        db.close()


async def rebuild_knowledge_base_background(user_id: int, kb_id: int):
    from app.core.logging import logger

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
        if not user or not kb:
            return

        documents = (
            db.query(Document)
            .filter(Document.knowledge_base_id == kb_id)
            .order_by(Document.created_at.asc(), Document.id.asc())
            .all()
        )
        for document in documents:
            document.status = DocumentStatus.PROCESSING
            document.error_message = None
        db.commit()

        await rebuild_kb_runtime(db, user, kb, documents)
    except Exception as exc:
        logger.exception("Knowledge-base rebuild failed: {}: {}", exc.__class__.__name__, exc)
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
        documents = db.query(Document).filter(Document.knowledge_base_id == kb_id).all()
        for document in documents:
            document.status = DocumentStatus.FAILED
            document.error_message = f"{exc.__class__.__name__}: {exc}"[:500]
        if kb:
            kb.is_initialized = False
            kb.total_chunks = 0
        db.commit()
    finally:
        db.close()


@router.post("/upload", response_model=DocSchema, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    kb_id: int = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kb = _get_owned_kb(db, current_user.id, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未提供文件名，请重新上传。",
        )
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in settings.get_allowed_extensions():
        allowed = ", ".join(settings.get_allowed_extensions())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件类型: {file_ext}。支持的类型: {allowed}",
        )

    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        limit_mb = settings.MAX_UPLOAD_SIZE / 1024 / 1024
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件过大，最大允许 {limit_mb:.0f}MB",
        )

    from app.utils.document_parser import extract_text
    try:
        text_content = extract_text(file.filename, content)
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except (ValueError, Exception) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件解析失败: {exc}",
        ) from exc

    if not text_content or not text_content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件内容为空或无法提取有效文本。",
        )

    doc = Document(name=file.filename, file_type=file_ext, file_size=len(content), knowledge_base_id=kb_id, content=text_content, status=DocumentStatus.PENDING)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    background_tasks.add_task(process_document_background, doc.id, current_user.id, kb_id, text_content)
    return doc


@router.get("/{doc_id}", response_model=DocSchema)
async def get_document(doc_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    doc, kb = _get_owned_document(db, current_user.id, doc_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if not kb:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return doc


@router.get("/{doc_id}/progress")
async def get_document_progress(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """轻量级进度查询端点，前端轮询时使用以减少流量。"""
    doc, kb = _get_owned_document(db, current_user.id, doc_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if not kb:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return {
        "id": doc.id,
        "status": doc.status,
        "progress": getattr(doc, "progress", 0) or 0,
        "progress_stage": getattr(doc, "progress_stage", "") or "",
        "error_message": doc.error_message,
    }


@router.post("/{doc_id}/reprocess", response_model=DocSchema)
async def reprocess_document(
    doc_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc, kb = _get_owned_document(db, current_user.id, doc_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if not kb:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    documents = db.query(Document).filter(Document.knowledge_base_id == kb.id).all()
    for item in documents:
        item.status = DocumentStatus.PROCESSING
        item.error_message = None
    kb.is_initialized = False
    db.commit()

    background_tasks.add_task(rebuild_knowledge_base_background, current_user.id, kb.id)
    db.refresh(doc)
    return doc


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc, kb = _get_owned_document(db, current_user.id, doc_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if not kb:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    remaining_documents = (
        db.query(Document)
        .filter(Document.knowledge_base_id == kb.id, Document.id != doc.id)
        .order_by(Document.created_at.asc(), Document.id.asc())
        .all()
    )

    if not remaining_documents:
        await cleanup_kb_runtime(current_user.id, kb.id)
        db.delete(doc)
        kb.document_count = 0
        kb.total_chunks = 0
        kb.is_initialized = False
        db.commit()
        return None

    # Only trigger a full rebuild when the deleted document was actually indexed
    # (status=completed). If it failed or was never processed, the stored index
    # already doesn't contain it — a rebuild would waste time and tokens.
    doc_was_indexed = doc.status == DocumentStatus.COMPLETED

    if not doc_was_indexed:
        # Safe fast-path: just remove the DB record; the index is unchanged.
        db.delete(doc)
        kb.document_count = len(remaining_documents)
        # Keep is_initialized / total_chunks as-is if the KB was already ready.
        db.commit()
        return None

    llm_provider, llm_api_key, embedding_api_key, _embedding_model = get_provider_keys(db, current_user.id)
    if llm_provider and llm_api_key and embedding_api_key:
        # Deletion should not be blocked by rebuild failures. We delete & commit first,
        # then rebuild the KB runtime in the background.
        for item in remaining_documents:
            item.status = DocumentStatus.PROCESSING
            item.error_message = None
            item.chunk_count = 0
            item.processed_at = None

        db.delete(doc)
        kb.document_count = len(remaining_documents)
        kb.total_chunks = 0
        kb.is_initialized = False
        db.commit()

        background_tasks.add_task(rebuild_knowledge_base_background, current_user.id, kb.id)
        return None

    await cleanup_kb_runtime(current_user.id, kb.id)
    for item in remaining_documents:
        item.status = DocumentStatus.PENDING
        item.error_message = "Knowledge base runtime needs rebuild after document deletion."
        item.chunk_count = 0
        item.processed_at = None
    db.delete(doc)
    kb.document_count = len(remaining_documents)
    kb.total_chunks = 0
    kb.is_initialized = False
    db.commit()
    return None
