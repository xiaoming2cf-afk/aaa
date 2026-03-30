from __future__ import annotations

from openai import OpenAI

from .config import Settings
from .entities import IntegrationCredential
from .provider_catalog import apply_provider_defaults, get_provider_spec
from .security import decrypt_secret


class ProviderGateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def test_integration(self, integration: IntegrationCredential) -> dict:
        resolved_base_url = self._resolved_base_url(integration)
        resolved_model = self._resolve_model(integration)
        provider = get_provider_spec(integration.kind, self.settings.model) or {}
        text = self.generate_markdown(
            integration=integration,
            system_prompt="You are a concise integration health check assistant.",
            user_prompt="Reply with a short sentence confirming the integration is working.",
            max_output_tokens=80,
        )
        return {
            "status": "ok",
            "preview": text,
            "provider_name": provider.get("label", integration.kind),
            "resolved_model": resolved_model,
            "resolved_base_url": resolved_base_url,
        }

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
        base_url = self._resolved_base_url(integration)
        if base_url:
            return OpenAI(api_key=api_key, base_url=base_url)
        return OpenAI(api_key=api_key)

    def _default_base_url(self, kind: str) -> str:
        base_url, _, _ = apply_provider_defaults(
            kind=kind,
            base_url="",
            model="",
            default_openai_model=self.settings.model,
        )
        return base_url

    def _resolved_base_url(self, integration: IntegrationCredential) -> str:
        base_url, _, _ = apply_provider_defaults(
            kind=integration.kind,
            base_url=integration.base_url,
            model=integration.model,
            default_openai_model=self.settings.model,
        )
        return base_url

    def _resolve_model(self, integration: IntegrationCredential) -> str:
        _, model, _ = apply_provider_defaults(
            kind=integration.kind,
            base_url=integration.base_url,
            model=integration.model,
            default_openai_model=self.settings.model,
        )
        return model or self.settings.model
