"""
文档相关的 Pydantic 模型
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class DocumentBase(BaseModel):
    """文档基础模型"""
    name: str = Field(..., min_length=1, max_length=255)


class DocumentCreate(DocumentBase):
    """创建文档"""
    knowledge_base_id: int
    content: Optional[str] = None
    file_type: Optional[str] = None


class DocumentUpdate(BaseModel):
    """更新文档"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)


class Document(DocumentBase):
    """文档响应模型"""
    id: int
    knowledge_base_id: int
    file_path: Optional[str]
    file_size: Optional[int]
    file_type: Optional[str]
    status: str
    error_message: Optional[str]
    progress: int = 0
    progress_stage: Optional[str] = ""
    chunk_count: int
    created_at: datetime
    updated_at: datetime
    processed_at: Optional[datetime]
    
    # 添加 filename 别名以兼容前端
    @property
    def filename(self) -> str:
        return self.name
    
    class Config:
        from_attributes = True
