from __future__ import annotations

from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .entities import IntegrationCredential, RuntimeBundle, RuntimeProfile, User, Workspace
from .provider_catalog import is_local_provider_kind
from .runtime_models import ProviderCapabilityMatrix, RuntimeProfileRequest, StageProviderBinding


_DEFAULT_CAPABILITY_BY_KIND: dict[str, ProviderCapabilityMatrix] = {
    "ollama": ProviderCapabilityMatrix(
        provider_kind="ollama",
        supports_structured_output=True,
        supports_tool_calls=True,
        supports_multimodal_input=True,
    ),
    "lmstudio": ProviderCapabilityMatrix(
        provider_kind="lmstudio",
        supports_structured_output=True,
        supports_tool_calls=True,
        supports_multimodal_input=False,
    ),
    "vllm": ProviderCapabilityMatrix(
        provider_kind="vllm",
        supports_structured_output=True,
        supports_tool_calls=True,
        supports_multimodal_input=False,
    ),
    "local_openai_compatible": ProviderCapabilityMatrix(
        provider_kind="local_openai_compatible",
        supports_structured_output=True,
        supports_tool_calls=True,
        supports_multimodal_input=False,
    ),
}


def _binding_dump(binding: StageProviderBinding) -> dict[str, Any]:
    return binding.model_dump(mode="json")


def _profile_dump(profile: RuntimeProfile) -> dict[str, Any]:
    active_bundle_payload = None
    if getattr(profile, "active_bundle_id", None):
        try:
            from .runtime_bundles import serialize_runtime_bundle

            active_bundle = getattr(profile, "_active_bundle_ref", None)
            if active_bundle is not None:
                active_bundle_payload = serialize_runtime_bundle(active_bundle)
        except Exception:
            active_bundle_payload = None
    bindings_payload = profile.bindings_json.get("bindings", []) if isinstance(profile.bindings_json, dict) else []
    bindings = [
        StageProviderBinding.model_validate(item)
        for item in bindings_payload
        if isinstance(item, dict)
    ]
    return {
        "id": profile.id,
        "workspace_id": profile.workspace_id,
        "owner_user_id": profile.owner_user_id,
        "name": profile.name,
        "description": profile.description,
        "is_default": profile.is_default,
        "bindings": [_binding_dump(binding) for binding in bindings],
        "active_bundle_id": getattr(profile, "active_bundle_id", None),
        "active_bundle_version": (
            str(active_bundle_payload.get("version") or "")
            if isinstance(active_bundle_payload, dict)
            else ""
        ),
        "active_bundle": active_bundle_payload,
        "health": dict(profile.health_json or {}) if isinstance(profile.health_json, dict) else {},
        "metadata": dict(profile.metadata_json or {}) if isinstance(profile.metadata_json, dict) else {},
        "created_at": profile.created_at.isoformat(),
        "updated_at": profile.updated_at.isoformat(),
    }


def serialize_runtime_profile(profile: RuntimeProfile) -> dict[str, Any]:
    return _profile_dump(profile)


def provider_capabilities_for_integration(integration: IntegrationCredential) -> ProviderCapabilityMatrix:
    base = _DEFAULT_CAPABILITY_BY_KIND.get(
        integration.kind,
        ProviderCapabilityMatrix(provider_kind=integration.kind),
    )
    config = dict(integration.config_json or {}) if isinstance(integration.config_json, dict) else {}
    return base.model_copy(
        update={
            "supports_structured_output": bool(
                config.get("supports_structured_output", base.supports_structured_output)
            ),
            "supports_tool_calls": bool(config.get("supports_tool_calls", base.supports_tool_calls)),
            "supports_multimodal_input": bool(
                config.get("supports_multimodal_input", base.supports_multimodal_input)
            ),
            "supports_long_form_writing": bool(
                config.get("supports_long_form_writing", base.supports_long_form_writing)
            ),
        }
    )


def _ensure_local_integration(integration: IntegrationCredential) -> IntegrationCredential:
    if not is_local_provider_kind(integration.kind):
        raise ValueError("Research runtime only supports local or self-hosted model integrations.")
    return integration


def get_runtime_profile_for_workspace(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    runtime_profile_id: str,
) -> RuntimeProfile:
    profile = db.scalar(
        select(RuntimeProfile).where(
            and_(
                RuntimeProfile.id == runtime_profile_id,
                RuntimeProfile.workspace_id == workspace.id,
                RuntimeProfile.owner_user_id == user.id,
            )
        )
    )
    if profile is None:
        raise FileNotFoundError("Runtime profile not found.")
    if getattr(profile, "active_bundle_id", None):
        profile._active_bundle_ref = db.get(RuntimeBundle, profile.active_bundle_id)  # type: ignore[attr-defined]
    return profile


def list_runtime_profiles(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
) -> list[RuntimeProfile]:
    profiles = list(
        db.scalars(
            select(RuntimeProfile)
            .where(
                and_(
                    RuntimeProfile.owner_user_id == user.id,
                    RuntimeProfile.workspace_id == workspace.id,
                )
            )
            .order_by(RuntimeProfile.is_default.desc(), RuntimeProfile.updated_at.desc())
        )
    )
    bundle_ids = [profile.active_bundle_id for profile in profiles if getattr(profile, "active_bundle_id", None)]
    bundles = {bundle.id: bundle for bundle in db.scalars(select(RuntimeBundle).where(RuntimeBundle.id.in_(bundle_ids)))} if bundle_ids else {}
    for profile in profiles:
        if getattr(profile, "active_bundle_id", None):
            profile._active_bundle_ref = bundles.get(profile.active_bundle_id)  # type: ignore[attr-defined]
    return profiles


def create_runtime_profile(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    request: RuntimeProfileRequest,
) -> RuntimeProfile:
    seen_integration_ids = {
        binding.integration_id
        for binding in request.bindings
    } | {
        integration_id
        for binding in request.bindings
        for integration_id in binding.fallback_integration_ids
    }
    for integration_id in seen_integration_ids:
        integration = db.scalar(
            select(IntegrationCredential).where(
                and_(
                    IntegrationCredential.id == integration_id,
                    IntegrationCredential.owner_user_id == user.id,
                )
            )
        )
        if integration is None:
            raise FileNotFoundError(f"Integration not found: {integration_id}")
        _ensure_local_integration(integration)
    if request.is_default:
        for existing in list_runtime_profiles(db, user=user, workspace=workspace):
            existing.is_default = False
    profile = RuntimeProfile(
        workspace_id=workspace.id,
        owner_user_id=user.id,
        name=request.name.strip(),
        description=request.description.strip(),
        is_default=request.is_default,
        bindings_json={"bindings": [_binding_dump(binding) for binding in request.bindings]},
        metadata_json=dict(request.metadata or {}),
    )
    db.add(profile)
    db.flush()
    return profile


def resolve_runtime_profile(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    runtime_profile_id: str | None = None,
) -> RuntimeProfile | None:
    if runtime_profile_id:
        return get_runtime_profile_for_workspace(
            db,
            user=user,
            workspace=workspace,
            runtime_profile_id=runtime_profile_id,
        )
    profile = db.scalar(
        select(RuntimeProfile).where(
            and_(
                RuntimeProfile.owner_user_id == user.id,
                RuntimeProfile.workspace_id == workspace.id,
                RuntimeProfile.is_default.is_(True),
            )
        )
    )
    if profile is not None:
        return profile
    default_integration = db.scalar(
        select(IntegrationCredential).where(
            and_(
                IntegrationCredential.owner_user_id == user.id,
                IntegrationCredential.category == "llm",
                IntegrationCredential.is_default.is_(True),
            )
        )
    )
    if default_integration is None:
        return None
    _ensure_local_integration(default_integration)
    bindings = [
        StageProviderBinding(stage=stage, integration_id=default_integration.id)
        for stage in ("planner", "researcher", "writer", "reviewer")
    ]
    synthetic = RuntimeProfile(
        workspace_id=workspace.id,
        owner_user_id=user.id,
        name="Default Runtime Profile",
        description="Synthetic profile derived from the default LLM integration.",
        is_default=True,
        bindings_json={"bindings": [_binding_dump(binding) for binding in bindings]},
        metadata_json={"synthetic": True},
    )
    return synthetic


def resolve_stage_binding(
    *,
    profile: RuntimeProfile | None,
    stage: str,
) -> StageProviderBinding | None:
    if profile is None or not isinstance(profile.bindings_json, dict):
        return None
    for item in profile.bindings_json.get("bindings", []):
        if not isinstance(item, dict):
            continue
        binding = StageProviderBinding.model_validate(item)
        if binding.stage == stage:
            return binding
    return None


def resolve_stage_integrations(
    db: Session,
    *,
    user: User,
    profile: RuntimeProfile | None,
    stage: str,
) -> list[IntegrationCredential]:
    binding = resolve_stage_binding(profile=profile, stage=stage)
    if binding is None:
        default_integration = db.scalar(
            select(IntegrationCredential).where(
                and_(
                    IntegrationCredential.owner_user_id == user.id,
                    IntegrationCredential.category == "llm",
                    IntegrationCredential.is_default.is_(True),
                )
            )
        )
        return [default_integration] if default_integration is not None else []
    integration_ids = [binding.integration_id, *binding.fallback_integration_ids]
    resolved: list[IntegrationCredential] = []
    seen: set[str] = set()
    for integration_id in integration_ids:
        if integration_id in seen:
            continue
        seen.add(integration_id)
        integration = db.scalar(
            select(IntegrationCredential).where(
                and_(
                    IntegrationCredential.id == integration_id,
                    IntegrationCredential.owner_user_id == user.id,
                )
            )
        )
        if integration is not None:
            resolved.append(_ensure_local_integration(integration))
    return resolved


def stage_provider_snapshot(
    *,
    stage: str,
    integration: IntegrationCredential,
    model_override: str = "",
) -> dict[str, Any]:
    capabilities = provider_capabilities_for_integration(integration)
    return {
        "stage": stage,
        "integration_id": integration.id,
        "label": integration.label,
        "kind": integration.kind,
        "model": model_override.strip() or integration.model,
        "capabilities": capabilities.model_dump(mode="json"),
    }
