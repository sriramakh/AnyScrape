from __future__ import annotations

from typing import List, Dict, Any, Iterable

from openai import OpenAI

from .config import get_settings


class LLMAgent:
    """
    Thin wrapper around OpenAI chat completions using gpt-4o-mini.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model

    def complete(
        self,
        system_prompt: str,
        messages: Iterable[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> str:
        """
        Call the chat completion API and return the assistant content.
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


