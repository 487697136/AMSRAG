"""
文档模型
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
import enum

from app.db.base import Base


class DocumentStatus(str, enum.Enum):
    """文档状态"""
    PENDING = "pending"  # 待处理
    PROCESSING = "processing"  # 处理中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败


class Document(Base):
    """文档表"""
    
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    file_path = Column(String(500))  # 文件存储路径
    file_size = Column(Integer)  # 文件大小（字节）
    file_type = Column(String(50))  # 文件类型（.txt, .md, .json等）
    
    # 所属知识库
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False)
    
    # 文档内容（小文件直接存储，大文件存储路径）
    content = Column(Text)
    
    # 处理状态
    status = Column(SQLEnum(DocumentStatus), default=DocumentStatus.PENDING)
    error_message = Column(Text)  # 错误信息
    
    # 统计信息
    chunk_count = Column(Integer, default=0)  # 分块数量
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    processed_at = Column(DateTime)  # 处理完成时间
    
    # 关系
    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    
    def __repr__(self):
        return f"<Document(id={self.id}, name='{self.name}', status='{self.status}')>"
