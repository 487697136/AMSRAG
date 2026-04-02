"""
日志配置
使用 loguru 进行日志管理
"""

import sys
from loguru import logger
from pathlib import Path

from .config import settings


def setup_logging():
    """配置日志系统"""
    
    # 移除默认的 handler
    logger.remove()
    
    # 添加控制台输出
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=settings.LOG_LEVEL,
        colorize=True,
    )
    
    # 添加文件输出
    log_file = Path(settings.LOG_FILE)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    logger.add(
        settings.LOG_FILE,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=settings.LOG_LEVEL,
        rotation="10 MB",  # 日志文件达到 10MB 时轮转
        retention="30 days",  # 保留 30 天
        compression="zip",  # 压缩旧日志
        encoding="utf-8",
    )
    
    logger.info(f"日志系统初始化完成 - Level: {settings.LOG_LEVEL}")
    logger.info(f"日志文件: {settings.LOG_FILE}")


# 导出 logger 实例
__all__ = ["logger", "setup_logging"]
