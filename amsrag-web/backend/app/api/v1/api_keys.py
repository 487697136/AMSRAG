"""API key management endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.api_key import APIKey
from app.models.user import User
from app.schemas.api_key import APIKey as APIKeySchema
from app.schemas.api_key import APIKeyCreate, APIKeyUpdate
from app.services.rag_service import clear_rag_service_cache
from app.utils.crypto import encrypt_api_key

router = APIRouter()


@router.get("/", response_model=List[APIKeySchema])
async def list_api_keys(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(APIKey).filter(APIKey.user_id == current_user.id).all()


@router.get("/providers")
async def list_providers(current_user: User = Depends(get_current_user)):
    from app.schemas.api_key import PROVIDER_REGISTRY
    return PROVIDER_REGISTRY


@router.get("/runtime-status")
async def get_runtime_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.schemas.api_key import SUPPORTED_PROVIDERS
    api_keys = db.query(APIKey).filter(APIKey.user_id == current_user.id).all()
    provider_status = {
        provider: next((item for item in api_keys if item.provider == provider), None) is not None
        for provider in SUPPORTED_PROVIDERS
    }

    neo4j_status = {
        "configured": bool(settings.NEO4J_URL and settings.get_neo4j_auth()),
        "connected": False,
        "message": None,
        "url": settings.NEO4J_URL or None,
    }
    if neo4j_status["configured"]:
        try:
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver(settings.NEO4J_URL, auth=settings.get_neo4j_auth())
            try:
                driver.verify_connectivity()
                neo4j_status["connected"] = True
                neo4j_status["message"] = "Neo4j connectivity verified."
            finally:
                driver.close()
        except Exception as exc:
            neo4j_status["message"] = str(exc)
    else:
        neo4j_status["message"] = "Neo4j is not configured."

    return {
        "app": {"name": settings.APP_NAME, "version": settings.APP_VERSION},
        "user": {"id": current_user.id, "username": current_user.username},
        "providers": provider_status,
        "graph_backend_requested": settings.RAG_GRAPH_BACKEND,
        "neo4j": neo4j_status,
        "upload": {
            "max_upload_size": settings.MAX_UPLOAD_SIZE,
            "allowed_extensions": settings.get_allowed_extensions(),
        },
        "paths": {
            "workspace_root": settings.RAG_WORKSPACE_DIR,
            "upload_root": settings.UPLOAD_DIR,
        },
    }


@router.post("/", response_model=APIKeySchema, status_code=status.HTTP_201_CREATED)
async def create_api_key(key_in: APIKeyCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    existing_key = (
        db.query(APIKey)
        .filter(APIKey.user_id == current_user.id, APIKey.provider == key_in.provider)
        .first()
    )
    if existing_key:
        existing_key.encrypted_key = encrypt_api_key(key_in.api_key)
        existing_key.description = key_in.description
        db.commit()
        db.refresh(existing_key)
        clear_rag_service_cache(current_user.id)
        return existing_key

    api_key = APIKey(
        user_id=current_user.id,
        provider=key_in.provider,
        encrypted_key=encrypt_api_key(key_in.api_key),
        description=key_in.description,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    clear_rag_service_cache(current_user.id)
    return api_key


@router.put("/{key_id}", response_model=APIKeySchema)
async def update_api_key(key_id: int, key_in: APIKeyUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    api_key = (
        db.query(APIKey)
        .filter(APIKey.id == key_id, APIKey.user_id == current_user.id)
        .first()
    )
    if not api_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")
    if key_in.api_key:
        api_key.encrypted_key = encrypt_api_key(key_in.api_key)
    if key_in.description is not None:
        api_key.description = key_in.description
    db.commit()
    db.refresh(api_key)
    clear_rag_service_cache(current_user.id)
    return api_key


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(key_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    api_key = (
        db.query(APIKey)
        .filter(APIKey.id == key_id, APIKey.user_id == current_user.id)
        .first()
    )
    if not api_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")
    db.delete(api_key)
    db.commit()
    clear_rag_service_cache(current_user.id)
    return None
