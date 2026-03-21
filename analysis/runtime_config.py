"""Runtime configuration for local and CML chatbot modes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
import os


@dataclass(frozen=True)
class RuntimeConfig:
    llm_provider: str
    llm_base_url: str
    llm_model: str
    llm_api_key: str | None
    primary_kb_path: Path
    secondary_kb_path: Path
    agentic_enabled: bool
    semantic_enabled: bool
    cml_round_mode: bool


def load_runtime_config(base_dir: Path, *, environ: Mapping[str, str] | None = None) -> RuntimeConfig:
    env = environ or os.environ
    provider = (env.get("OENB_LLM_PROVIDER") or "ollama").strip().lower()

    if provider == "mistral":
        base_url = (env.get("OENB_MISTRAL_BASE_URL") or "").strip()
        model = (env.get("OENB_MISTRAL_MODEL") or "").strip()
        api_key = (env.get("OENB_MISTRAL_API_KEY") or "").strip() or None
    else:
        provider = "ollama"
        base_url = (env.get("OENB_OLLAMA_BASE_URL") or "http://localhost:11434").strip()
        model = (env.get("OENB_OLLAMA_MODEL") or "qwen2.5:3b").strip()
        api_key = None

    data_dir = base_dir / "data"
    return RuntimeConfig(
        llm_provider=provider,
        llm_base_url=base_url,
        llm_model=model,
        llm_api_key=api_key,
        primary_kb_path=data_dir / "statistics_production" / "knowledge_base_active.jsonl",
        secondary_kb_path=data_dir / "full_site_production" / "knowledge_base_active.jsonl",
        agentic_enabled=_env_flag(env.get("OENB_AGENTIC_ENABLED")),
        semantic_enabled=_env_flag(env.get("OENB_SEMANTIC_ENABLED")),
        cml_round_mode=_env_flag(env.get("OENB_CML_ROUND_MODE")),
    )


def _env_flag(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
