from __future__ import annotations

from openai import OpenAI

from .config import Settings
from .entities import IntegrationCredential
from .security import decrypt_secret


GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
ANTHROPIC_OPENAI_BASE_URL = "https://api.anthropic.com/v1/"


class ProviderGateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def test_integration(self, integration: IntegrationCredential) -> dict:
        text = self.generate_markdown(
            integration=integration,
            system_prompt="You are a concise integration health check assistant.",
            user_prompt="Reply with a short sentence confirming the integration is working.",
            max_output_tokens=80,
        )
        return {"status": "ok", "preview": text}

    def generate_markdown(
        self,
        *,
        integration: IntegrationCredential,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int = 1200,
    ) -> str:
        client = self._build_client(integration)
        response = client.chat.completions.create(
            model=self._resolve_model(integration),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_output_tokens,
        )
        message = response.choices[0].message
        return message.content or ""

    def _build_client(self, integration: IntegrationCredential) -> OpenAI:
        api_key = decrypt_secret(self.settings, integration.api_key_encrypted)
        base_url = (integration.base_url or "").strip() or self._default_base_url(integration.kind)
        if base_url:
            return OpenAI(api_key=api_key, base_url=base_url)
        return OpenAI(api_key=api_key)

    def _default_base_url(self, kind: str) -> str:
        if kind == "gemini":
            return GEMINI_OPENAI_BASE_URL
        if kind == "anthropic":
            return ANTHROPIC_OPENAI_BASE_URL
        return ""

    def _resolve_model(self, integration: IntegrationCredential) -> str:
        if integration.model:
            return integration.model
        defaults = {
            "openai": self.settings.model,
            "openai_compatible": self.settings.model,
            "gemini": "gemini-2.5-flash",
            "anthropic": "claude-sonnet-4-0",
        }
        return defaults.get(integration.kind, self.settings.model)
