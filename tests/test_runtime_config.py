import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.runtime_config import load_runtime_config


def test_load_runtime_config_resolves_local_ollama_settings(tmp_path: Path):
    config = load_runtime_config(
        tmp_path,
        environ={
            "OENB_LLM_PROVIDER": "ollama",
            "OENB_OLLAMA_BASE_URL": "http://localhost:11434",
            "OENB_OLLAMA_MODEL": "qwen2.5:3b",
        },
    )

    assert config.llm_provider == "ollama"
    assert config.llm_base_url == "http://localhost:11434"
    assert config.llm_model == "qwen2.5:3b"


def test_load_runtime_config_resolves_cml_mistral_settings(tmp_path: Path):
    config = load_runtime_config(
        tmp_path,
        environ={
            "OENB_LLM_PROVIDER": "mistral",
            "OENB_MISTRAL_BASE_URL": "https://mistral.internal",
            "OENB_MISTRAL_MODEL": "mistral-large",
            "OENB_MISTRAL_API_KEY": "secret-token",
        },
    )

    assert config.llm_provider == "mistral"
    assert config.llm_base_url == "https://mistral.internal"
    assert config.llm_model == "mistral-large"
    assert config.llm_api_key == "secret-token"


def test_load_runtime_config_uses_default_active_kb_paths(tmp_path: Path):
    config = load_runtime_config(tmp_path, environ={})

    assert config.primary_kb_path == tmp_path / "data" / "statistics_production" / "knowledge_base_active.jsonl"
    assert config.secondary_kb_path == tmp_path / "data" / "full_site_production" / "knowledge_base_active.jsonl"


def test_load_runtime_config_reads_round_crawl_compatibility_flags(tmp_path: Path):
    config = load_runtime_config(
        tmp_path,
        environ={
            "OENB_AGENTIC_ENABLED": "1",
            "OENB_SEMANTIC_ENABLED": "true",
            "OENB_CML_ROUND_MODE": "yes",
        },
    )

    assert config.agentic_enabled is True
    assert config.semantic_enabled is True
    assert config.cml_round_mode is True
