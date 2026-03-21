"""Shared LLM provider interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    base_url: str
    model: str
    api_key: str | None = None
    timeout_seconds: float = 30.0


class LLMProvider(ABC):
    """Minimal interface shared across Ollama and CML-hosted models."""

    def __init__(
        self,
        *,
        provider_name: str,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.provider_name = provider_name
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    @abstractmethod
    def invoke_text(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def invoke_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema_hint: str | None = None,
    ) -> dict:
        raise NotImplementedError

