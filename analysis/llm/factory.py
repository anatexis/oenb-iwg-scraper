"""Factory for switching between local Ollama and CML-hosted Mistral."""

from __future__ import annotations

import os
from collections.abc import Mapping

from analysis.llm.base import LLMConfig, LLMProvider
from analysis.llm.mistral_provider import MistralProvider
from analysis.llm.ollama_provider import OllamaProvider


def build_llm_provider(
    config: LLMConfig | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> LLMProvider:
    if config is None:
        config = _config_from_environ(environ or os.environ)
    _validate_config(config)

    provider = config.provider.strip().lower()
    if provider == "ollama":
        return OllamaProvider(
            base_url=config.base_url,
            model=config.model,
            api_key=config.api_key,
            timeout_seconds=config.timeout_seconds,
        )
    if provider == "mistral":
        return MistralProvider(
            base_url=config.base_url,
            model=config.model,
            api_key=config.api_key,
            timeout_seconds=config.timeout_seconds,
        )
    raise ValueError(f"Unsupported LLM provider: {config.provider}")


def _config_from_environ(environ: Mapping[str, str]) -> LLMConfig:
    provider = (environ.get("OENB_LLM_PROVIDER") or "ollama").strip().lower()
    if provider == "ollama":
        return LLMConfig(
            provider=provider,
            base_url=(
                environ.get("OENB_OLLAMA_BASE_URL")
                or environ.get("OLLAMA_BASE_URL")
                or environ.get("OENB_LLM_BASE_URL")
                or "http://localhost:11434"
            ).strip(),
            model=(
                environ.get("OENB_OLLAMA_MODEL")
                or environ.get("OLLAMA_MODEL")
                or environ.get("OENB_LLM_MODEL")
                or "qwen2.5:3b"
            ).strip(),
            api_key=(
                environ.get("OENB_OLLAMA_API_KEY")
                or environ.get("OLLAMA_API_KEY")
                or environ.get("OENB_LLM_API_KEY")
                or ""
            ).strip()
            or None,
        )
    if provider == "mistral":
        return LLMConfig(
            provider=provider,
            base_url=(
                environ.get("OENB_MISTRAL_BASE_URL")
                or environ.get("MISTRAL_BASE_URL")
                or environ.get("OENB_LLM_BASE_URL")
                or ""
            ).strip(),
            model=(environ.get("OENB_MISTRAL_MODEL") or environ.get("MISTRAL_MODEL") or environ.get("OENB_LLM_MODEL") or "").strip(),
            api_key=(
                environ.get("OENB_MISTRAL_API_KEY")
                or environ.get("MISTRAL_API_KEY")
                or environ.get("OENB_LLM_API_KEY")
                or ""
            ).strip()
            or None,
        )
    return LLMConfig(
        provider=provider,
        base_url=(environ.get("OENB_LLM_BASE_URL") or "").strip(),
        model=(environ.get("OENB_LLM_MODEL") or "").strip(),
        api_key=(environ.get("OENB_LLM_API_KEY") or "").strip() or None,
    )


def _validate_config(config: LLMConfig) -> None:
    if not config.base_url:
        raise ValueError("Missing required LLM config: base_url")
    if not config.model:
        raise ValueError("Missing required LLM config: model")
