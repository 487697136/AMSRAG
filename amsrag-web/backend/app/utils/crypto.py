"""
加密工具
用于加密和解密 API 密钥
"""

import base64
from cryptography.fernet import Fernet
from app.core.config import settings


def _get_cipher():
    """获取加密器"""
    # 使用 SECRET_KEY 的前 32 字节作为加密密钥
    key = base64.urlsafe_b64encode(settings.SECRET_KEY[:32].encode().ljust(32)[:32])
    return Fernet(key)


def encrypt_api_key(api_key: str) -> str:
    """
    加密 API 密钥
    
    Args:
        api_key: 原始 API 密钥
    
    Returns:
        加密后的密钥（Base64 编码）
    """
    cipher = _get_cipher()
    encrypted = cipher.encrypt(api_key.encode())
    return base64.b64encode(encrypted).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    """
    解密 API 密钥
    
    Args:
        encrypted_key: 加密的 API 密钥
    
    Returns:
        原始 API 密钥
    """
    cipher = _get_cipher()
    encrypted_bytes = base64.b64decode(encrypted_key.encode())
    decrypted = cipher.decrypt(encrypted_bytes)
    return decrypted.decode()
