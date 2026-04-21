import inspect
import json
import numpy as np
from typing import Optional, List, Any, Callable, Awaitable

import aioboto3
from openai import AsyncOpenAI, AsyncAzureOpenAI, APIConnectionError, RateLimitError

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
import os
import httpx

from ._utils import compute_args_hash, wrap_embedding_func_with_attrs, logger
import asyncio
from functools import lru_cache
from typing import Dict


from .base import BaseKVStorage

global_openai_async_client = None
global_azure_openai_async_client = None
global_amazon_bedrock_async_client = None
_hf_tokenizer_cache: Dict[str, Any] = {}
_hf_model_cache: Dict[str, Any] = {}


def get_openai_async_client_instance():
    global global_openai_async_client
    if global_openai_async_client is None:
        # 兼容 DashScope OpenAI 接口：当检测到 DASHSCOPE_API_KEY 时，优先走 DashScope 端点
        dashscope_api_key = os.getenv("DASHSCOPE_API_KEY", "")
        # 兼容 SiliconFlow OpenAI 接口：当检测到 SILKFLOW_API_KEY 时，走 SiliconFlow 端点
        silkflow_api_key = os.getenv("SILKFLOW_API_KEY", "")
        if dashscope_api_key:
            base_url = os.getenv(
                "DASHSCOPE_API_BASE",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
            global_openai_async_client = AsyncOpenAI(
                base_url=base_url, api_key=dashscope_api_key
            )
        elif silkflow_api_key:
            base_url = os.getenv("SILKFLOW_API_BASE", "https://api.siliconflow.cn/v1")
            global_openai_async_client = AsyncOpenAI(
                base_url=base_url, api_key=silkflow_api_key
            )
        else:
            # 默认走 OpenAI 官方（需要 OPENAI_API_KEY）
            global_openai_async_client = AsyncOpenAI()
    return global_openai_async_client


def get_azure_openai_async_client_instance():
    global global_azure_openai_async_client
    if global_azure_openai_async_client is None:
        global_azure_openai_async_client = AsyncAzureOpenAI()
    return global_azure_openai_async_client


def get_amazon_bedrock_async_client_instance():
    global global_amazon_bedrock_async_client
    if global_amazon_bedrock_async_client is None:
        global_amazon_bedrock_async_client = aioboto3.Session()
    return global_amazon_bedrock_async_client


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
)
async def openai_complete_if_cache(
    model, prompt, system_prompt=None, history_messages=[], **kwargs
) -> str:
    _bound_client = kwargs.pop("_bound_client", None)
    openai_async_client = _bound_client if _bound_client is not None else get_openai_async_client_instance()
    hashing_kv: BaseKVStorage = kwargs.pop("hashing_kv", None)
    stream_callback = kwargs.pop("stream_callback", None)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history_messages)
    messages.append({"role": "user", "content": prompt})
    if hashing_kv is not None:
        args_hash = compute_args_hash(model, messages)
        if_cache_return = await hashing_kv.get_by_id(args_hash)
        if if_cache_return is not None:
            if stream_callback:
                await _emit_stream_callback(stream_callback, if_cache_return["return"])
            return if_cache_return["return"]

    if stream_callback:
        stream = await openai_async_client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            **kwargs,
        )
        response_chunks: list[str] = []
        async for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            content = getattr(delta, "content", None) if delta is not None else None
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict)
                )
            if not content:
                continue
            response_chunks.append(content)
            await _emit_stream_callback(stream_callback, content)
        response_text = "".join(response_chunks)
    else:
        response = await openai_async_client.chat.completions.create(
            model=model, messages=messages, **kwargs
        )
        response_text = response.choices[0].message.content

    if hashing_kv is not None:
        await hashing_kv.upsert(
            {args_hash: {"return": response_text, "model": model}}
        )
        await hashing_kv.index_done_callback()
    return response_text


async def _emit_stream_callback(
    stream_callback: Callable[[str], Any] | Callable[[str], Awaitable[Any]],
    content: str,
) -> None:
    if not stream_callback or not content:
        return
    callback_result = stream_callback(content)
    if inspect.isawaitable(callback_result):
        await callback_result


def create_openai_compatible_complete_function(
    model_id: str,
    client: Optional["AsyncOpenAI"] = None,
) -> Callable:
    """创建绑定到指定客户端（或默认全局客户端）的 OpenAI 兼容补全函数。

    通过 ``client`` 参数传入专属 ``AsyncOpenAI`` 实例，可避免多个 RAG 服务实例
    共享全局客户端时因端点/Key 互相覆盖而导致的"Model Not Exist"等错误。
    """
    async def openai_compatible_complete(
        prompt: str,
        system_prompt: Optional[str] = None,
        history_messages: List[Any] = [],
        **kwargs,
    ) -> str:
        return await openai_complete_if_cache(
            model_id,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            _bound_client=client,
            **kwargs,
        )

    openai_compatible_complete.__name__ = f"{model_id.replace('-', '_')}_complete"
    return openai_compatible_complete


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
)
async def amazon_bedrock_complete_if_cache(
    model, prompt, system_prompt=None, history_messages=[], **kwargs
) -> str:
    amazon_bedrock_async_client = get_amazon_bedrock_async_client_instance()
    hashing_kv: BaseKVStorage = kwargs.pop("hashing_kv", None)
    messages = []
    messages.extend(history_messages)
    messages.append({"role": "user", "content": [{"text": prompt}]})
    if hashing_kv is not None:
        args_hash = compute_args_hash(model, messages)
        if_cache_return = await hashing_kv.get_by_id(args_hash)
        if if_cache_return is not None:
            return if_cache_return["return"]

    inference_config = {
        "temperature": 0,
        "maxTokens": 4096 if "max_tokens" not in kwargs else kwargs["max_tokens"],
    }

    async with amazon_bedrock_async_client.client(
        "bedrock-runtime",
        region_name=os.getenv("AWS_REGION", "us-east-1")
    ) as bedrock_runtime:
        if system_prompt:
            response = await bedrock_runtime.converse(
                modelId=model, messages=messages, inferenceConfig=inference_config,
                system=[{"text": system_prompt}]
            )
        else:
            response = await bedrock_runtime.converse(
                modelId=model, messages=messages, inferenceConfig=inference_config,
            )

    if hashing_kv is not None:
        await hashing_kv.upsert(
            {args_hash: {"return": response["output"]["message"]["content"][0]["text"], "model": model}}
        )
        await hashing_kv.index_done_callback()
    return response["output"]["message"]["content"][0]["text"]


def create_amazon_bedrock_complete_function(model_id: str) -> Callable:
    """
    Factory function to dynamically create completion functions for Amazon Bedrock

    Args:
        model_id (str): Amazon Bedrock model identifier (e.g., "us.anthropic.claude-3-sonnet-20240229-v1:0")

    Returns:
        Callable: Generated completion function
    """
    async def bedrock_complete(
        prompt: str,
        system_prompt: Optional[str] = None,
        history_messages: List[Any] = [],
        **kwargs
    ) -> str:
        return await amazon_bedrock_complete_if_cache(
            model_id,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            **kwargs
        )
    
    # Set function name for easier debugging
    bedrock_complete.__name__ = f"{model_id}_complete"
    
    return bedrock_complete


async def gpt_4o_complete(
    prompt, system_prompt=None, history_messages=[], **kwargs
) -> str:
    return await openai_complete_if_cache(
        "gpt-4o",
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        **kwargs,
    )


async def gpt_4o_mini_complete(
    prompt, system_prompt=None, history_messages=[], **kwargs
) -> str:
    return await openai_complete_if_cache(
        "gpt-4o-mini",
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        **kwargs,
    )


async def qwen_turbo_complete(
    prompt, system_prompt=None, history_messages=[], **kwargs
) -> str:
    """DashScope Qwen Turbo 的 OpenAI 兼容补全函数。"""
    return await openai_complete_if_cache(
        "qwen-turbo",
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        **kwargs,
    )


async def qwen_plus_complete(
    prompt, system_prompt=None, history_messages=[], **kwargs
) -> str:
    return await openai_complete_if_cache(
        "qwen-plus",
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        **kwargs,
    )


async def qwen_flash_complete(
    prompt, system_prompt=None, history_messages=[], **kwargs
) -> str:
    return await openai_complete_if_cache(
        "qwen-flash",
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        **kwargs,
    )


@wrap_embedding_func_with_attrs(embedding_dim=1024, max_token_size=8192)
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
)
async def amazon_bedrock_embedding(texts: list[str]) -> np.ndarray:
    amazon_bedrock_async_client = get_amazon_bedrock_async_client_instance()

    async with amazon_bedrock_async_client.client(
        "bedrock-runtime",
        region_name=os.getenv("AWS_REGION", "us-east-1")
    ) as bedrock_runtime:
        embeddings = []
        for text in texts:
            body = json.dumps(
                {
                    "inputText": text,
                    "dimensions": 1024,
                }
            )
            response = await bedrock_runtime.invoke_model(
                modelId="amazon.titan-embed-text-v2:0", body=body,
            )
            response_body = await response.get("body").read()
            embeddings.append(json.loads(response_body))
    return np.array([dp["embedding"] for dp in embeddings])


@wrap_embedding_func_with_attrs(embedding_dim=1536, max_token_size=8192)
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
)
async def openai_embedding(texts: list[str]) -> np.ndarray:
    openai_async_client = get_openai_async_client_instance()
    response = await openai_async_client.embeddings.create(
        model="text-embedding-3-small", input=texts, encoding_format="float"
    )
    return np.array([dp.embedding for dp in response.data])


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
)
async def azure_openai_complete_if_cache(
    deployment_name, prompt, system_prompt=None, history_messages=[], **kwargs
) -> str:
    azure_openai_client = get_azure_openai_async_client_instance()
    hashing_kv: BaseKVStorage = kwargs.pop("hashing_kv", None)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history_messages)
    messages.append({"role": "user", "content": prompt})
    if hashing_kv is not None:
        args_hash = compute_args_hash(deployment_name, messages)
        if_cache_return = await hashing_kv.get_by_id(args_hash)
        if if_cache_return is not None:
            return if_cache_return["return"]

    response = await azure_openai_client.chat.completions.create(
        model=deployment_name, messages=messages, **kwargs
    )

    if hashing_kv is not None:
        await hashing_kv.upsert(
            {
                args_hash: {
                    "return": response.choices[0].message.content,
                    "model": deployment_name,
                }
            }
        )
        await hashing_kv.index_done_callback()
    return response.choices[0].message.content


async def azure_gpt_4o_complete(
    prompt, system_prompt=None, history_messages=[], **kwargs
) -> str:
    return await azure_openai_complete_if_cache(
        "gpt-4o",
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        **kwargs,
    )


async def azure_gpt_4o_mini_complete(
    prompt, system_prompt=None, history_messages=[], **kwargs
) -> str:
    return await azure_openai_complete_if_cache(
        "gpt-4o-mini",
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        **kwargs,
    )


@wrap_embedding_func_with_attrs(embedding_dim=1536, max_token_size=8192)
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
)
async def azure_openai_embedding(texts: list[str]) -> np.ndarray:
    azure_openai_client = get_azure_openai_async_client_instance()
    response = await azure_openai_client.embeddings.create(
        model="text-embedding-3-small", input=texts, encoding_format="float"
    )
    return np.array([dp.embedding for dp in response.data])


@wrap_embedding_func_with_attrs(embedding_dim=1024, max_token_size=8192)
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((httpx.ReadTimeout, httpx.ConnectTimeout,
                                  httpx.HTTPStatusError)),
)
async def siliconflow_embedding(texts: list[str]) -> np.ndarray:
    """调用硅基流动 BGE-M3 嵌入服务。

    说明：
        - 默认模型为 ``BAAI/bge-m3``，维度 1024。
        - 支持通过环境变量覆写：
          - ``SILKFLOW_API_KEY``: 授权密钥（必需）
          - ``SILKFLOW_API_BASE``: 基础 URL，默认
            ``https://api.siliconflow.cn/v1``
          - ``SILKFLOW_EMBED_MODEL``: 模型名，默认 ``BAAI/bge-m3``

    参数：
        texts: 需要编码的文本列表。

    返回：
        ``np.ndarray``，形状为 ``(len(texts), 1024)``。
    """

    # 兼容两种环境变量命名：SILKFLOW_* 与 SILICONFLOW_*
    api_key = (
        os.environ.get("SILKFLOW_API_KEY", "").strip()
        or os.environ.get("SILICONFLOW_API_KEY", "").strip()
    )
    if not api_key:
        raise ValueError("未提供 SILKFLOW_API_KEY")

    api_base = (
        os.environ.get("SILKFLOW_API_BASE", "").strip()
        or os.environ.get("SILICONFLOW_API_BASE", "").strip()
        or "https://api.siliconflow.cn/v1"
    ).rstrip("/")
    model = (
        os.environ.get("SILKFLOW_EMBED_MODEL", "").strip()
        or os.environ.get("SILICONFLOW_EMBED_MODEL", "").strip()
        or "BAAI/bge-m3"
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "input": texts,
        "encoding_format": "float",
    }

    async def _do_request(use_model: str) -> np.ndarray:
        payload["model"] = use_model
        async with httpx.AsyncClient(timeout=120.0) as client:
            logger.info(
                "正在发送嵌入请求到 %s/embeddings (model=%s)", api_base, use_model
            )
            response = await client.post(
                f"{api_base}/embeddings", headers=headers, json=payload
            )
            response.raise_for_status()
            result = response.json()
            embeddings = [item["embedding"] for item in result["data"]]
            return np.array(embeddings)

    try:
        return await _do_request(model)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            # Pro 版模型需要付费账号，自动降级到免费版
            if model.startswith("Pro/"):
                fallback_model = model[len("Pro/"):]
                logger.warning(
                    "嵌入模型 %s 返回 403（无访问权限或额度不足），"
                    "自动降级到免费版 %s。建议在「设置」页面将嵌入模型改为 %s。",
                    model, fallback_model, fallback_model,
                )
                # 降级后仍然让异常向上传播，以便调用方能感知失败
                return await _do_request(fallback_model)
            else:
                logger.error(
                    "硅基流动嵌入 API 403 Forbidden（模型=%s）。"
                    "可能原因：API Key 已过期/无效、账号额度耗尽，或该模型需要付费权限。"
                    "请前往「设置 → 模型密钥」检查并更新 SiliconFlow API Key。",
                    model,
                )
        else:
            logger.error("硅基流动嵌入 API 请求失败（HTTP %s）: %s", exc.response.status_code, str(exc))
        # 抛出异常而不是返回随机向量，防止用垃圾数据污染 FAISS 索引
        raise RuntimeError(f"硅基流动嵌入 API 调用失败（模型={model}）: {exc}") from exc
    except Exception as exc:
        logger.error("硅基流动嵌入 API 请求失败: %s", str(exc))
        # 同样抛出异常，让建库流程感知到错误，而不是静默写入无效向量
        raise RuntimeError(f"硅基流动嵌入 API 调用失败（模型={model}）: {exc}") from exc
