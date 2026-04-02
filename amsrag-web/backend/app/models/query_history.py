"""
查询历史模型
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship

from app.db.base import Base


class QueryHistory(Base):
    """查询历史表"""
    
    __tablename__ = "query_histories"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 查询信息
    question = Column(Text, nullable=False)
    answer = Column(Text)
    mode = Column(String(20))  # naive, local, global, mix
    
    # 所属用户和知识库
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False)
    
    # 性能指标
    response_time = Column(Float)  # 响应时间（秒）
    token_count = Column(Integer)  # Token 数量
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    user = relationship("User", back_populates="query_histories")
    knowledge_base = relationship("KnowledgeBase", back_populates="query_histories")
    
    def __repr__(self):
        return f"<QueryHistory(id={self.id}, question='{self.question[:50]}...', mode='{self.mode}')>"
