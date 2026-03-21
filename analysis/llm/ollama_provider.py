"""Ollama-backed provider."""

from __future__ import annotations

import json

import requests

from analysis.llm.base import LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        super().__init__(
            provider_name="ollama",
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )

    def invoke_text(self, system_prompt: str, user_prompt: str) -> str:
        response = self._generate(system_prompt, user_prompt)
        return str(response.get("response", "")).strip()

    def invoke_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema_hint: str | None = None,
    ) -> dict:
        prompt = user_prompt
        if schema_hint:
            prompt = f"{user_prompt}\n\nReturn JSON matching this schema hint:\n{schema_hint}"
        response = self._generate(system_prompt, prompt, json_mode=True)
        payload = response.get("response", "{}")
        if isinstance(payload, dict):
            return payload
        return json.loads(payload)

    def _generate(self, system_prompt: str, user_prompt: str, json_mode: bool = False) -> dict:
        body = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
        }
        if json_mode:
            body["format"] = "json"
        response = requests.post(
            f"{self.base_url}/api/generate",
            json=body,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

