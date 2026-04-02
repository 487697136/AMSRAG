"""
知识库模型
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from app.db.base import Base


class KnowledgeBase(Base):
    """知识库表"""
    
    __tablename__ = "knowledge_bases"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    
    # 所有者
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # RAG 配置
    enable_local = Column(Boolean, default=True)
    enable_naive_rag = Column(Boolean, default=True)
    enable_bm25 = Column(Boolean, default=False)
    
    # 统计信息
    document_count = Column(Integer, default=0)
    total_chunks = Column(Integer, default=0)
    
    # 状态
    is_initialized = Column(Boolean, default=False)  # RAG 实例是否已初始化
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    owner = relationship("User", back_populates="knowledge_bases")
    documents = relationship("Document", back_populates="knowledge_base", cascade="all, delete-orphan")
    query_histories = relationship("QueryHistory", back_populates="knowledge_base", cascade="all, delete-orphan")
    conversation_sessions = relationship(
        "ConversationSession",
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self):
        return f"<KnowledgeBase(id={self.id}, name='{self.name}', owner_id={self.owner_id})>"
