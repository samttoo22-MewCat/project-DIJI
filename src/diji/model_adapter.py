"""Model adapters and routing decisions matching ai-server's supported backends."""

from __future__ import annotations

import os
from typing import Protocol

import httpx
from openai import AsyncOpenAI
from .provider_routing import provider_client

from .domain import ModelConfiguration


class ModelAdapter(Protocol):
    async def generate(self, config: ModelConfiguration, messages: list[dict[str, str]]) -> str: ...


def is_digi_model(model_name: str) -> bool:
    return model_name.upper().startswith("DIGI") or model_name in {"Joi", "DIJI-Joi"}


def is_orpo_remote(config: ModelConfiguration) -> bool:
    return "100.108.209.35" in (config.url or "") or config.model in {"orpo", "/models/orpo_merged_qwen35_gptq"}


class AiServerCompatibleAdapter:
    """Route OpenAI-compatible, vLLM, and ORPO requests with ai-server's payloads."""

    def __init__(self, openrouter_api_key: str | None = None) -> None:
        self.openrouter_api_key = openrouter_api_key

    async def generate(self, config: ModelConfiguration, messages: list[dict[str, str]]) -> str:
        if is_digi_model(config.model):
            return await self._vllm(config, messages)
        if is_orpo_remote(config):
            return await self._orpo(config, messages)
        return await self._openai_compatible(config, messages)

    async def _openai_compatible(self, config: ModelConfiguration, messages: list[dict[str, str]]) -> str:
        model = config.model or "deepseek/deepseek-v4.1-flash"
        if model.startswith("skylark-"):
            base_url, api_key = "https://ark.ap-southeast.bytepluses.com/api/v3", os.getenv("ARK_API_KEY", "")
        else:
            base_url, api_key = config.url or "https://openrouter.ai/api/v1", self.openrouter_api_key or os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            raise RuntimeError("A configured provider key is required before a model request can be sent")
        client = provider_client(base_url=base_url, api_key=api_key)
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=config.parameters.max_tokens,
            temperature=config.parameters.temperature,
            top_p=config.parameters.top_p,
        )
        return response.choices[0].message.content or ""

    async def _vllm(self, config: ModelConfiguration, messages: list[dict[str, str]]) -> str:
        base_url = os.getenv("VLLM_API_URL", "http://100.108.209.35:8000").rstrip("/") + "/v1"
        client = AsyncOpenAI(base_url=base_url, api_key=os.getenv("VLLM_API_KEY", "EMPTY"))
        response = await client.chat.completions.create(
            model="/models/orpo_merged_qwen35_gptq",
            messages=messages,
            max_tokens=config.parameters.max_tokens,
            temperature=config.parameters.temperature,
            top_p=config.parameters.top_p,
            seed=42,
            extra_body={"repetition_penalty": 1.1, "use_adapter": True},
        )
        return response.choices[0].message.content or ""

    async def _orpo(self, config: ModelConfiguration, messages: list[dict[str, str]]) -> str:
        base_url = (config.url or os.getenv("EVAL_API_URL", "http://100.108.209.35:8000")).rstrip("/")
        if "100.108.209.35" not in base_url:
            base_url = os.getenv("EVAL_API_URL", "http://100.108.209.35:8000").rstrip("/")
        payload = {
            "messages": messages,
            "use_adapter": True,
            "max_new_tokens": config.parameters.max_tokens,
            "temperature": config.parameters.temperature,
            "top_p": config.parameters.top_p,
            "repetition_penalty": 1.1,
            "seed": 42,
            "model": "/models/orpo_merged_qwen35_gptq" if config.model == "orpo" else config.model,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(f"{base_url}/api/generate", json=payload)
            response.raise_for_status()
        return response.json()["output"]
