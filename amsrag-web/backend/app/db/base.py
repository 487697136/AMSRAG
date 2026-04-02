"""
数据库 Base 类
所有模型的基类
"""

from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

# 导入所有模型，确保 Alembic 可以检测到
# 这些导入会在 alembic/env.py 中使用
from app.models.user import User  # noqa
from app.models.knowledge_base import KnowledgeBase  # noqa
from app.models.document import Document  # noqa
from app.models.query_history import QueryHistory  # noqa
from app.models.api_key import APIKey  # noqa
from app.models.conversation import ConversationSession, ConversationTurn  # noqa
