from __future__ import annotations

from .config import Settings
from .entities import IntegrationCredential
from .provider_catalog import apply_provider_defaults, get_provider_spec
from .runtime_provider import RuntimeProviderError, build_runtime_client
from .security import validate_provider_base_url


class ProviderGatewayError(RuntimeError):
    pass


class ProviderGateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _build_client(self, integration: IntegrationCredential):
        return build_runtime_client(settings=self.settings, integration=integration)

    def test_integration(self, integration: IntegrationCredential) -> dict:
        resolved_base_url = self._resolved_base_url(integration)
        resolved_model = self._resolve_model(integration)
        provider = get_provider_spec(integration.kind, self.settings.model) or {}
        try:
            text = self.generate_markdown(
                integration=integration,
                system_prompt="You are a concise integration health check assistant.",
                user_prompt="Reply with a short sentence confirming the integration is working.",
                max_output_tokens=80,
            )
        except ProviderGatewayError as exc:
            return {
                "status": "error",
                "preview": "Connection test failed.",
                "reason": str(exc),
                "provider_name": provider.get("label", integration.kind),
                "resolved_model": resolved_model,
                "resolved_base_url": resolved_base_url,
            }
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
        try:
            responses_api = getattr(client, "responses", None)
            if responses_api is not None and hasattr(responses_api, "create"):
                response = responses_api.create(
                    model=self._resolve_model(integration),
                    instructions=system_prompt,
                    input=user_prompt,
                )
                return response.output_text or ""
            chat_api = getattr(getattr(client, "chat", None), "completions", None)
            if chat_api is None or not hasattr(chat_api, "create"):
                raise ProviderGatewayError("Provider client is not compatible.")
            response = chat_api.create(
                model=self._resolve_model(integration),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_output_tokens,
            )
        except RuntimeProviderError as exc:
            raise ProviderGatewayError(str(exc)) from exc
        except ProviderGatewayError:
            raise
        except Exception as exc:
            raise ProviderGatewayError("Provider request failed.") from exc

        choice = ((getattr(response, "choices", None) or [{}])[0]) if response is not None else {}
        message = choice.get("message") if isinstance(choice, dict) else getattr(choice, "message", None)
        if isinstance(message, dict):
            return str(message.get("content") or "")
        return str(getattr(message, "content", "") or "")

    def _resolved_base_url(self, integration: IntegrationCredential) -> str:
        base_url, _, _ = apply_provider_defaults(
            kind=integration.kind,
            base_url=integration.base_url,
            model=integration.model,
            default_openai_model=self.settings.model,
        )
        return validate_provider_base_url(self.settings, base_url)

    def _resolve_model(self, integration: IntegrationCredential) -> str:
        _, model, _ = apply_provider_defaults(
            kind=integration.kind,
            base_url=integration.base_url,
            model=integration.model,
            default_openai_model=self.settings.model,
        )
        return model or self.settings.model
