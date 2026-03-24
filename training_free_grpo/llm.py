from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(slots=True)
class Message:
    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(slots=True)
class Response:
    content: str
    raw: dict[str, Any]


class ChatLLM(ABC):
    @abstractmethod
    def chat(self, messages: list[Message], *, temperature: float = 0.2, max_tokens: int = 2048) -> Response:
        raise NotImplementedError


class OpenAICompatibleLLM(ChatLLM):
    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    def chat(self, messages: list[Message], *, temperature: float = 0.2, max_tokens: int = 2048) -> Response:
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                if isinstance(content, list):
                    content = "\n".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
                return Response(content=str(content), raw=data)
            except Exception as exc:
                last_error = exc
                if attempt == self.max_retries:
                    break
                time.sleep(min(2**attempt, 8))
        raise RuntimeError(f"LLM request failed after {self.max_retries} attempts: {last_error}") from last_error
