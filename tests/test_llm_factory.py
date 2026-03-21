import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.llm.factory import LLMConfig, build_llm_provider
from analysis.llm.mistral_provider import MistralProvider
from analysis.llm.ollama_provider import OllamaProvider


def test_build_llm_provider_returns_ollama_provider_for_explicit_config():
    provider = build_llm_provider(
        LLMConfig(
            provider="ollama",
            base_url="http://localhost:11434",
            model="qwen2.5:3b",
        )
    )

    assert isinstance(provider, OllamaProvider)
    assert provider.provider_name == "ollama"
    assert provider.base_url == "http://localhost:11434"
    assert provider.model == "qwen2.5:3b"


def test_build_llm_provider_returns_mistral_provider_from_environment():
    provider = build_llm_provider(
        environ={
            "OENB_LLM_PROVIDER": "mistral",
            "MISTRAL_BASE_URL": "https://mistral.internal",
            "MISTRAL_MODEL": "mistral-large",
            "MISTRAL_API_KEY": "secret-token",
        }
    )

    assert isinstance(provider, MistralProvider)
    assert provider.provider_name == "mistral"
    assert provider.base_url == "https://mistral.internal"
    assert provider.model == "mistral-large"
    assert provider.api_key == "secret-token"


def test_build_llm_provider_raises_clear_error_for_missing_required_config():
    with pytest.raises(ValueError, match="base_url"):
        build_llm_provider(LLMConfig(provider="ollama", base_url="", model=""))


def test_build_llm_provider_raises_clear_error_for_unknown_provider():
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        build_llm_provider(LLMConfig(provider="wat", base_url="http://example", model="x"))
