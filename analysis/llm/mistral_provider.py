"""Mistral-compatible provider for CML-hosted endpoints."""

from __future__ import annotations

import json

import requests

from analysis.llm.base import LLMProvider


class MistralProvider(LLMProvider):
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        super().__init__(
            provider_name="mistral",
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )

    def invoke_text(self, system_prompt: str, user_prompt: str) -> str:
        payload = self._chat(system_prompt, user_prompt)
        message = payload["choices"][0]["message"]["content"]
        return str(message).strip()

    def invoke_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema_hint: str | None = None,
    ) -> dict:
        prompt = user_prompt
        if schema_hint:
            prompt = f"{user_prompt}\n\nReturn JSON matching this schema hint:\n{schema_hint}"
        payload = self._chat(system_prompt, prompt, json_mode=True)
        message = payload["choices"][0]["message"]["content"]
        if isinstance(message, dict):
            return message
        return json.loads(message)

    def _chat(self, system_prompt: str, user_prompt: str, json_mode: bool = False) -> dict:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        response = requests.post(
            f"{self.base_url}/v1/chat/completions",
            json=body,
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

