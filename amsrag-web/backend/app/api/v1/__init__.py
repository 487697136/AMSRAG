"""API v1 路由"""

from fastapi import APIRouter
from .auth import router as auth_router
from .knowledge_bases import router as kb_router
from .documents import router as doc_router
from .query import router as query_router
from .api_keys import router as apikey_router

api_router = APIRouter()

# 注册子路由
api_router.include_router(auth_router, prefix="/auth", tags=["认证"])
api_router.include_router(kb_router, prefix="/knowledge-bases", tags=["知识库"])
api_router.include_router(doc_router, prefix="/documents", tags=["文档"])
api_router.include_router(query_router, prefix="/query", tags=["查询"])
api_router.include_router(apikey_router, prefix="/api-keys", tags=["API密钥"])
