"""
API 密钥模型
用于存储用户的第三方 API 密钥（加密存储）
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.db.base import Base


class APIKey(Base):
    """API 密钥表"""
    
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 所属用户
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # API 提供商
    provider = Column(String(50), nullable=False)  # dashscope, siliconflow 等
    
    # 加密后的 API 密钥
    encrypted_key = Column(Text, nullable=False)
    
    # 密钥描述
    description = Column(String(255))

    # 嵌入模型名称（仅对 embedding 类型的 provider 有效）
    # 例：BAAI/bge-m3 或 Pro/BAAI/bge-m3
    model_name = Column(String(100))
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    user = relationship("User", back_populates="api_keys")
    
    def __repr__(self):
        return f"<APIKey(id={self.id}, provider='{self.provider}', user_id={self.user_id})>"
