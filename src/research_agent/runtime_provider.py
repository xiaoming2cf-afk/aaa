from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

import requests
from pydantic import BaseModel

from .config import Settings
from .entities import IntegrationCredential
from .provider_catalog import apply_provider_defaults
from .runtime_profiles import provider_capabilities_for_integration
from .security import decrypt_secret, validate_provider_base_url


_DEFAULT_TIMEOUT_SECONDS = 45.0


class RuntimeProviderError(RuntimeError):
    pass


@dataclass
class RuntimeFunctionToolCall:
    call_id: str
    name: str
    arguments: str
    type: str = "function_call"


@dataclass
class RuntimeOutputText:
    text: str
    type: str = "output_text"


@dataclass
class RuntimeMessage:
    content: list[RuntimeOutputText]
    type: str = "message"


@dataclass
class RuntimeResponse:
    id: str
    output_text: str = ""
    output_parsed: Any = None
    output: list[Any] | None = None


def _normalize_message_text(input_payload: Any) -> str:
    if isinstance(input_payload, str):
        return input_payload
    if isinstance(input_payload, list):
        lines: list[str] = []
        for item in input_payload:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "function_call_output":
                lines.append(str(item.get("output") or ""))
                continue
            content = item.get("content")
            if isinstance(content, str):
                lines.append(content)
                continue
            if isinstance(content, list):
                for chunk in content:
                    if not isinstance(chunk, dict):
                        continue
                    chunk_type = str(chunk.get("type") or "")
                    if chunk_type == "input_text":
                        lines.append(str(chunk.get("text") or ""))
                    elif chunk_type == "input_image":
                        lines.append("[Image attachment included]")
                    elif chunk_type == "input_file":
                        lines.append(f"[File attachment: {chunk.get('filename') or 'file'}]")
        return "\n".join(line for line in lines if line.strip())
    return str(input_payload or "")


def _convert_input_to_messages(input_payload: Any) -> list[dict[str, Any]]:
    if isinstance(input_payload, str):
        return [{"role": "user", "content": input_payload}]
    if not isinstance(input_payload, list):
        return [{"role": "user", "content": str(input_payload or "")}]

    provider_messages: list[dict[str, Any]] = []
    for item in input_payload:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "function_call_output":
            provider_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(item.get("call_id") or ""),
                    "content": str(item.get("output") or ""),
                }
            )
            continue
        role = str(item.get("role") or "user")
        content = item.get("content")
        if isinstance(content, str):
            provider_messages.append({"role": role, "content": content})
            continue
        if isinstance(content, list):
            parts: list[Any] = []
            for chunk in content:
                if not isinstance(chunk, dict):
                    continue
                chunk_type = str(chunk.get("type") or "")
                if chunk_type == "input_text":
                    parts.append({"type": "text", "text": str(chunk.get("text") or "")})
                elif chunk_type == "input_image":
                    parts.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": str(chunk.get("image_url") or "")},
                        }
                    )
                elif chunk_type == "input_file":
                    parts.append(
                        {
                            "type": "text",
                            "text": f"[File attachment: {chunk.get('filename') or 'file'}]",
                        }
                    )
            if parts and all(part.get("type") == "text" for part in parts):
                provider_messages.append(
                    {"role": role, "content": "\n".join(str(part.get("text") or "") for part in parts)}
                )
            else:
                provider_messages.append({"role": role, "content": parts})
    return provider_messages or [{"role": "user", "content": _normalize_message_text(input_payload)}]


def _json_schema_instruction(schema_model: type[BaseModel]) -> str:
    schema = schema_model.model_json_schema()
    return (
        "Return valid JSON matching this schema exactly. Do not wrap the JSON in markdown fences.\n"
        f"{json.dumps(schema, ensure_ascii=False)}"
    )


def _parse_json_payload(text: str) -> Any:
    candidate = str(text or "").strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if "\n" in candidate:
            candidate = candidate.split("\n", 1)[1]
    return json.loads(candidate)


class OpenAICompatibleRuntimeAdapter:
    def __init__(
        self,
        *,
        settings: Settings,
        integration: IntegrationCredential,
        model_override: str = "",
    ) -> None:
        self.settings = settings
        self.integration = integration
        base_url, resolved_model, _ = apply_provider_defaults(
            kind=integration.kind,
            base_url=integration.base_url,
            model=model_override or integration.model,
            default_openai_model=settings.model,
        )
        self.base_url = validate_provider_base_url(settings, base_url)
        self.model = resolved_model or model_override or integration.model or settings.model
        self.api_key = (
            decrypt_secret(settings, integration.api_key_encrypted)
            if (integration.api_key_encrypted or "").strip()
            else ""
        )
        self.capabilities = provider_capabilities_for_integration(integration)

    def generate(
        self,
        *,
        instructions: str,
        input_payload: Any,
        schema_model: type[BaseModel] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> RuntimeResponse:
        messages = _convert_input_to_messages(input_payload)
        if instructions.strip():
            messages.insert(0, {"role": "system", "content": instructions.strip()})
        if schema_model is not None:
            messages.append({"role": "system", "content": _json_schema_instruction(schema_model)})
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if schema_model is not None and self.capabilities.supports_structured_output:
            payload["response_format"] = {"type": "json_object"}
        response_json = self._post_chat_completion(payload)
        choice = ((response_json.get("choices") or [{}])[0]) if isinstance(response_json, dict) else {}
        message = choice.get("message") or {}
        tool_calls = message.get("tool_calls") or []
        response_id = str(response_json.get("id") or f"runtime-{uuid.uuid4().hex}")
        if tool_calls:
            return RuntimeResponse(
                id=response_id,
                output_text="",
                output_parsed=None,
                output=[
                    RuntimeFunctionToolCall(
                        call_id=str(item.get("id") or f"call-{uuid.uuid4().hex}"),
                        name=str(((item.get("function") or {}).get("name")) or ""),
                        arguments=str(((item.get("function") or {}).get("arguments")) or "{}"),
                    )
                    for item in tool_calls
                ],
            )
        content = message.get("content") or ""
        if isinstance(content, list):
            text = "\n".join(
                str(item.get("text") or "")
                for item in content
                if isinstance(item, dict)
            ).strip()
        else:
            text = str(content).strip()
        parsed = None
        if schema_model is not None and text:
            parsed = schema_model.model_validate(_parse_json_payload(text))
        return RuntimeResponse(
            id=response_id,
            output_text=text,
            output_parsed=parsed,
            output=[RuntimeMessage(content=[RuntimeOutputText(text=text)])] if text else [],
        )

    def _post_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        base_url = self.base_url.rstrip("/")
        if not base_url:
            raise RuntimeProviderError("Runtime integration requires a base URL.")
        endpoint = f"{base_url}/chat/completions"
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key.strip():
                headers["Authorization"] = f"Bearer {self.api_key}"
            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=_DEFAULT_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise RuntimeProviderError("Provider request failed.") from exc
        if response.status_code in {401, 403}:
            raise RuntimeProviderError("Provider rejected the credentials.")
        if response.status_code >= 400:
            raise RuntimeProviderError(f"Provider request failed ({response.status_code}).")
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeProviderError("Provider returned non-JSON output.") from exc


class RuntimeResponsesAPI:
    def __init__(self, adapter: OpenAICompatibleRuntimeAdapter) -> None:
        self.adapter = adapter
        self._history_by_response_id: dict[str, list[dict[str, Any]]] = {}

    def create(self, **kwargs) -> RuntimeResponse:
        return self._run(schema_model=None, **kwargs)

    def parse(self, **kwargs) -> RuntimeResponse:
        schema_model = kwargs.pop("text_format", None)
        return self._run(schema_model=schema_model, **kwargs)

    def _run(
        self,
        *,
        schema_model: type[BaseModel] | None,
        model: str | None = None,
        instructions: str = "",
        input: Any = None,
        tools: list[dict[str, Any]] | None = None,
        previous_response_id: str | None = None,
        **_: Any,
    ) -> RuntimeResponse:
        history = list(self._history_by_response_id.get(previous_response_id or "", []))
        current_messages = _convert_input_to_messages(input)
        merged_messages = [*history, *current_messages]
        response = self.adapter.generate(
            instructions=instructions,
            input_payload=merged_messages,
            schema_model=schema_model if isinstance(schema_model, type) and issubclass(schema_model, BaseModel) else None,
            tools=tools,
        )
        if response.output and all(isinstance(item, RuntimeFunctionToolCall) for item in response.output):
            history_update = [*merged_messages, {"role": "assistant", "tool_calls": [item.__dict__ for item in response.output]}]
        else:
            history_update = [*merged_messages]
            if response.output_text:
                history_update.append({"role": "assistant", "content": response.output_text})
        self._history_by_response_id[response.id] = history_update
        return response


class RuntimeClient:
    def __init__(self, adapter: OpenAICompatibleRuntimeAdapter) -> None:
        self.responses = RuntimeResponsesAPI(adapter)


def build_runtime_client(
    *,
    settings: Settings,
    integration: IntegrationCredential,
    model_override: str = "",
) -> RuntimeClient:
    adapter = OpenAICompatibleRuntimeAdapter(
        settings=settings,
        integration=integration,
        model_override=model_override,
    )
    return RuntimeClient(adapter)
