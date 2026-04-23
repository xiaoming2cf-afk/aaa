from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import re
from typing import Any

import requests
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .config import Settings
from .entities import IntegrationCredential, User, Workspace
from .security import decrypt_secret, encrypt_secret, validate_provider_base_url
from .utils import truncate_text


AGENT_LLM_CATEGORY = "data_lab_agent_llm"
AGENT_LLM_KIND = "data_lab_openai_compatible"
_DEFAULT_TIMEOUT_SECONDS = 45


@dataclass(frozen=True)
class AgentLLMRuntimeConfig:
    enabled: bool
    source: str
    base_url: str = ""
    api_key: str = ""
    coder_model: str = ""
    reviewer_model: str = ""
    report_model: str = ""
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS
    label: str = ""

    @property
    def ready(self) -> bool:
        return bool(self.enabled and self.base_url.strip() and self.coder_model.strip())

    def model_for_role(self, role: str) -> str:
        normalized = role.strip().lower()
        if normalized == "reviewer":
            return self.reviewer_model or self.coder_model
        if normalized == "report":
            return self.report_model or self.coder_model
        return self.coder_model

    def public_summary(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "ready": self.ready,
            "source": self.source,
            "base_url_configured": bool(self.base_url.strip()),
            "api_key_configured": bool(self.api_key.strip()),
            "coder_model": self.coder_model,
            "reviewer_model": self.reviewer_model,
            "report_model": self.report_model,
            "timeout_seconds": self.timeout_seconds,
            "label": self.label,
        }


class AgentLLMError(RuntimeError):
    pass


class AgentLLMClient:
    def __init__(self, config: AgentLLMRuntimeConfig) -> None:
        if not config.ready:
            raise AgentLLMError("Data Lab Agent LLM config is not ready.")
        self.config = config

    def complete_json(
        self,
        *,
        role: str,
        instructions: str,
        input_payload: dict[str, Any],
        max_tokens: int = 1800,
    ) -> dict[str, Any]:
        text = self.complete_text(
            role=role,
            instructions=instructions,
            input_payload=input_payload,
            max_tokens=max_tokens,
        )
        return _extract_json_object(text)

    def complete_text(
        self,
        *,
        role: str,
        instructions: str,
        input_payload: dict[str, Any],
        max_tokens: int = 1800,
    ) -> str:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key.strip():
            headers["Authorization"] = f"Bearer {self.config.api_key.strip()}"
        payload = {
            "model": self.config.model_for_role(role),
            "messages": [
                {"role": "system", "content": instructions.strip()},
                {"role": "user", "content": json.dumps(input_payload, ensure_ascii=False)},
            ],
            "temperature": 0.15,
            "max_tokens": max(200, int(max_tokens)),
        }
        try:
            response = requests.post(
                _chat_completions_url(self.config.base_url),
                headers=headers,
                json=payload,
                timeout=max(1, int(self.config.timeout_seconds)),
            )
            response.raise_for_status()
            data = response.json()
        except requests.Timeout as exc:
            raise AgentLLMError("Data Lab Agent LLM request timed out.") from exc
        except requests.RequestException as exc:
            raise AgentLLMError("Data Lab Agent LLM request failed.") from exc
        except ValueError as exc:
            raise AgentLLMError("Data Lab Agent LLM returned non-JSON transport data.") from exc
        return _extract_text_from_chat_response(data)


def resolve_agent_llm_config(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
) -> AgentLLMRuntimeConfig:
    workspace_record = _workspace_llm_record(db, user=user, workspace=workspace)
    if workspace_record is not None:
        config_json = _config_dict(workspace_record)
        if bool(config_json.get("enabled", True)):
            return _runtime_config_from_record(settings, workspace_record)
    return _runtime_config_from_env(settings)


def get_agent_llm_config(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
) -> dict[str, Any]:
    workspace_record = _workspace_llm_record(db, user=user, workspace=workspace)
    workspace_payload: dict[str, Any] = {
        "configured": False,
        "enabled": False,
        "base_url": "",
        "api_key_configured": False,
        "coder_model": "",
        "reviewer_model": "",
        "report_model": "",
        "label": "",
    }
    if workspace_record is not None:
        config_json = _config_dict(workspace_record)
        workspace_payload = {
            "configured": True,
            "enabled": bool(config_json.get("enabled", True)),
            "base_url": workspace_record.base_url,
            "api_key_configured": bool((workspace_record.api_key_encrypted or "").strip()),
            "coder_model": str(config_json.get("coder_model") or workspace_record.model or ""),
            "reviewer_model": str(config_json.get("reviewer_model") or workspace_record.model or ""),
            "report_model": str(config_json.get("report_model") or workspace_record.model or ""),
            "label": workspace_record.label,
        }
    env_config = _runtime_config_from_env(settings)
    resolved = resolve_agent_llm_config(settings, db, user=user, workspace=workspace)
    return {
        "workspace": workspace_payload,
        "environment": {
            "enabled": env_config.enabled,
            "ready": env_config.ready,
            "base_url_configured": bool(env_config.base_url.strip()),
            "api_key_configured": bool(env_config.api_key.strip()),
            "coder_model": env_config.coder_model,
            "reviewer_model": env_config.reviewer_model,
            "report_model": env_config.report_model,
        },
        "resolved": resolved.public_summary(),
    }


def update_agent_llm_config(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    enabled: bool,
    base_url: str,
    api_key: str = "",
    clear_api_key: bool = False,
    coder_model: str = "",
    reviewer_model: str = "",
    report_model: str = "",
    label: str = "",
) -> dict[str, Any]:
    normalized_base_url = validate_provider_base_url(settings, str(base_url or "").strip())
    normalized_coder_model = _clean_model_name(coder_model)
    normalized_reviewer_model = _clean_model_name(reviewer_model) or normalized_coder_model
    normalized_report_model = _clean_model_name(report_model) or normalized_coder_model
    if enabled and not normalized_base_url:
        raise ValueError("Data Lab Agent LLM base_url is required when enabled.")
    if enabled and not normalized_coder_model:
        raise ValueError("Data Lab Agent coder model is required when enabled.")

    record = _workspace_llm_record(db, user=user, workspace=workspace)
    if record is None:
        record = IntegrationCredential(
            owner_user_id=user.id,
            category=AGENT_LLM_CATEGORY,
            kind=AGENT_LLM_KIND,
            label=(label.strip() or f"Data Lab Agent LLM {workspace.id[:8]}")[:120],
            api_key_encrypted="",
            base_url=normalized_base_url,
            model=normalized_coder_model,
            is_default=True,
            config_json={},
        )
        db.add(record)
    record.category = AGENT_LLM_CATEGORY
    record.kind = AGENT_LLM_KIND
    record.label = (label.strip() or record.label or f"Data Lab Agent LLM {workspace.id[:8]}")[:120]
    record.base_url = normalized_base_url
    record.model = normalized_coder_model
    record.is_default = True
    if clear_api_key:
        record.api_key_encrypted = ""
    elif api_key.strip():
        record.api_key_encrypted = encrypt_secret(settings, api_key.strip())
    record.config_json = {
        "workspace_id": workspace.id,
        "enabled": bool(enabled),
        "coder_model": normalized_coder_model,
        "reviewer_model": normalized_reviewer_model,
        "report_model": normalized_report_model,
        "provider_name": "Data Lab Agent scoped LLM",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    db.flush()
    return get_agent_llm_config(settings, db, user=user, workspace=workspace)


def test_agent_llm_config(
    settings: Settings,
    db: Session,
    *,
    user: User,
    workspace: Workspace,
) -> dict[str, Any]:
    config = resolve_agent_llm_config(settings, db, user=user, workspace=workspace)
    if not config.ready:
        return {
            "status": "unavailable",
            "preview": "Data Lab Agent LLM is not configured; rule-based fallback remains active.",
            "resolved": config.public_summary(),
        }
    try:
        payload = AgentLLMClient(config).complete_json(
            role="coder",
            instructions=(
                "Return only JSON with keys status and note. "
                "Use status='ok' when the Data Lab Agent scoped model endpoint is reachable."
            ),
            input_payload={"task": "connection_check"},
            max_tokens=200,
        )
    except AgentLLMError as exc:
        return {
            "status": "error",
            "preview": "Data Lab Agent LLM connection test failed.",
            "reason": str(exc),
            "resolved": config.public_summary(),
        }
    return {
        "status": "ok" if str(payload.get("status") or "").lower() == "ok" else "ok",
        "preview": truncate_text(str(payload.get("note") or "Data Lab Agent LLM endpoint responded."), 240),
        "resolved": config.public_summary(),
    }


def _workspace_llm_record(db: Session, *, user: User, workspace: Workspace) -> IntegrationCredential | None:
    rows = list(
        db.scalars(
            select(IntegrationCredential)
            .where(
                and_(
                    IntegrationCredential.owner_user_id == user.id,
                    IntegrationCredential.category == AGENT_LLM_CATEGORY,
                )
            )
            .order_by(IntegrationCredential.updated_at.desc())
        )
    )
    for row in rows:
        config_json = _config_dict(row)
        if str(config_json.get("workspace_id") or "") == workspace.id:
            return row
    return None


def _runtime_config_from_record(settings: Settings, record: IntegrationCredential) -> AgentLLMRuntimeConfig:
    config_json = _config_dict(record)
    api_key = decrypt_secret(settings, record.api_key_encrypted) if (record.api_key_encrypted or "").strip() else ""
    return AgentLLMRuntimeConfig(
        enabled=bool(config_json.get("enabled", True)),
        source="workspace",
        base_url=record.base_url,
        api_key=api_key,
        coder_model=str(config_json.get("coder_model") or record.model or ""),
        reviewer_model=str(config_json.get("reviewer_model") or record.model or ""),
        report_model=str(config_json.get("report_model") or record.model or ""),
        timeout_seconds=int(getattr(settings, "data_lab_agent_llm_timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)),
        label=record.label,
    )


def _runtime_config_from_env(settings: Settings) -> AgentLLMRuntimeConfig:
    enabled = bool(getattr(settings, "data_lab_agent_llm_enabled", False))
    raw_base_url = str(getattr(settings, "data_lab_agent_llm_base_url", "") or "").strip()
    base_url = validate_provider_base_url(settings, raw_base_url) if raw_base_url else ""
    coder_model = str(getattr(settings, "data_lab_agent_coder_model", "") or "").strip()
    reviewer_model = str(getattr(settings, "data_lab_agent_reviewer_model", "") or "").strip()
    report_model = str(getattr(settings, "data_lab_agent_report_model", "") or "").strip()
    return AgentLLMRuntimeConfig(
        enabled=enabled,
        source="environment" if enabled else "disabled",
        base_url=base_url,
        api_key=str(getattr(settings, "data_lab_agent_llm_api_key", "") or "").strip(),
        coder_model=coder_model,
        reviewer_model=reviewer_model or coder_model,
        report_model=report_model or coder_model,
        timeout_seconds=int(getattr(settings, "data_lab_agent_llm_timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)),
        label="Environment",
    )


def _config_dict(record: IntegrationCredential) -> dict[str, Any]:
    return dict(record.config_json or {}) if isinstance(record.config_json, dict) else {}


def _clean_model_name(value: str) -> str:
    return str(value or "").strip()[:120]


def _chat_completions_url(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _extract_text_from_chat_response(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first, dict) else {}
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = [
                    str(item.get("text") or "")
                    for item in content
                    if isinstance(item, dict) and str(item.get("type") or "text") in {"text", "output_text"}
                ]
                if parts:
                    return "\n".join(parts)
        text = first.get("text") if isinstance(first, dict) else ""
        if isinstance(text, str):
            return text
    output_text = data.get("output_text")
    if isinstance(output_text, str):
        return output_text
    raise AgentLLMError("Data Lab Agent LLM response did not include text content.")


def _extract_json_object(text: str) -> dict[str, Any]:
    candidate = str(text or "").strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate)
    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            candidate = candidate[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise AgentLLMError("Data Lab Agent LLM returned invalid JSON.") from exc
    if not isinstance(parsed, dict):
        raise AgentLLMError("Data Lab Agent LLM returned a non-object JSON payload.")
    return parsed
