"""API key schema definitions."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

SUPPORTED_LLM_PROVIDERS = [
    "dashscope",
    "openai",
    "deepseek",
    "zhipu",
    "moonshot",
    "openrouter",
]

SUPPORTED_EMBEDDING_PROVIDERS = [
    "siliconflow",
]

SUPPORTED_PROVIDERS = SUPPORTED_LLM_PROVIDERS + SUPPORTED_EMBEDDING_PROVIDERS

PROVIDER_REGISTRY = {
    "dashscope": {
        "label": "DashScope（通义千问）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "type": "llm",
        "default_models": ["qwen-plus", "qwen-turbo", "qwen-max", "qwen-long"],
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "type": "llm",
        "default_models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "type": "llm",
        "default_models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "zhipu": {
        "label": "智谱 AI（GLM）",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "type": "llm",
        "default_models": ["glm-4-plus", "glm-4-flash", "glm-4"],
    },
    "moonshot": {
        "label": "Moonshot（Kimi）",
        "base_url": "https://api.moonshot.cn/v1",
        "type": "llm",
        "default_models": ["moonshot-v1-auto", "moonshot-v1-8k", "moonshot-v1-32k"],
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "type": "llm",
        "default_models": ["anthropic/claude-3.5-sonnet", "google/gemini-2.0-flash-exp", "meta-llama/llama-3.1-70b-instruct"],
    },
    "siliconflow": {
        "label": "SiliconFlow（硅基流动）",
        "base_url": "https://api.siliconflow.cn/v1",
        "type": "embedding",
        "default_models": ["BAAI/bge-m3"],
    },
}

PROVIDER_PATTERN = "^(" + "|".join(SUPPORTED_PROVIDERS) + ")$"


class APIKeyBase(BaseModel):
    provider: str = Field(..., pattern=PROVIDER_PATTERN)
    description: Optional[str] = None


class APIKeyCreate(APIKeyBase):
    api_key: str = Field(..., min_length=10)


class APIKeyUpdate(BaseModel):
    api_key: Optional[str] = Field(None, min_length=10)
    description: Optional[str] = None


class APIKey(APIKeyBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
