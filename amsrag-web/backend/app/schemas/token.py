"""
Token 相关的 Pydantic 模型
"""

from typing import Optional
from pydantic import BaseModel


class Token(BaseModel):
    """Token 响应"""
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """Token 载荷"""
    sub: Optional[int] = None  # user_id
