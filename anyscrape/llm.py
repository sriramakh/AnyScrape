from __future__ import annotations

import asyncio
from typing import List, Dict, Any, Iterable

from openai import OpenAI, AsyncOpenAI

from .config import get_settings


class LLMAgent:
    """
    Thin wrapper around OpenAI chat completions using gpt-4o-mini.
    Supports both sync and async calls.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._async_client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model

    def complete(
        self,
        system_prompt: str,
        messages: Iterable[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> str:
        """
        Synchronous chat completion. Use for CLI or non-async contexts.
        """
        message_list: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        message_list.extend(messages)
        response = self._client.chat.completions.create(
            model=self._model,
            messages=message_list,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content or ""
        return content.strip()

    async def acomplete(
        self,
        system_prompt: str,
        messages: Iterable[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> str:
        """
        Async chat completion. Use in the web API path to avoid blocking
        the event loop.
        """
        message_list: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        message_list.extend(messages)
        response = await self._async_client.chat.completions.create(
            model=self._model,
            messages=message_list,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content or ""
        return content.strip()


