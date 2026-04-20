from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .entities import IntegrationCredential, RuntimeBundle, RuntimeProfile, User, Workspace
from .local_runtime import collect_local_runtime_health
from .orchestration_prompts import (
    PLANNER_INSTRUCTIONS,
    RESEARCHER_INSTRUCTIONS,
    REVIEWER_INSTRUCTIONS,
    WRITER_INSTRUCTIONS,
)
from .provider_catalog import is_local_provider_kind
from .provider_gateway import ProviderGateway
from .runtime_models import RuntimeBundleSummary
from .runtime_profiles import create_runtime_profile, get_runtime_profile_for_workspace
from .runtime_models import RuntimeProfileRequest, StageProviderBinding
from .utils import utc_timestamp_slug


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _bundle_prompt_defaults() -> dict[str, Any]:
    return {
        "planner": PLANNER_INSTRUCTIONS,
        "researcher": RESEARCHER_INSTRUCTIONS,
        "writer": WRITER_INSTRUCTIONS,
        "reviewer": REVIEWER_INSTRUCTIONS,
    }


def _default_review_thresholds() -> dict[str, Any]:
    return {
        "max_unsupported_claim_count": 0,
        "max_missing_sections": 0,
        "require_valid_source_ids": True,
    }


def _default_delivery_thresholds() -> dict[str, Any]:
    return {
        "required_total_score": 500,
        "required_dimension_score": 100,
        "required_citation_coverage": 1.0,
        "required_unsupported_claim_rate": 0.0,
        "required_review_block_precision": 1.0,
        "required_golden_eval_pass_rate": 1.0,
    }


def _default_routing_policy() -> dict[str, Any]:
    return {
        "production_mode": "local_only",
        "first_class_local_targets": ["ollama", "vllm"],
        "compatibility_targets": ["lmstudio", "local_openai_compatible"],
        "stage_preferences": {
            "planner": ["vllm", "ollama"],
            "researcher": ["vllm", "ollama"],
            "writer": ["ollama", "vllm"],
            "reviewer": ["vllm", "ollama"],
        },
    }


def serialize_runtime_bundle(bundle: RuntimeBundle) -> dict[str, Any]:
    payload = RuntimeBundleSummary(
        id=bundle.id,
        workspace_id=bundle.workspace_id,
        name=bundle.name,
        version=bundle.version,
        status=str(bundle.status or "draft"),
        prompts=dict(bundle.prompts_json or {}) if isinstance(bundle.prompts_json, dict) else {},
        rubric=dict(bundle.rubric_json or {}) if isinstance(bundle.rubric_json, dict) else {},
        routing_policy=dict(bundle.routing_policy_json or {}) if isinstance(bundle.routing_policy_json, dict) else {},
        review_thresholds=(
            dict(bundle.review_thresholds_json or {}) if isinstance(bundle.review_thresholds_json, dict) else {}
        ),
        delivery_thresholds=(
            dict(bundle.delivery_thresholds_json or {}) if isinstance(bundle.delivery_thresholds_json, dict) else {}
        ),
        eval_baseline=dict(bundle.eval_baseline_json or {}) if isinstance(bundle.eval_baseline_json, dict) else {},
        score=dict(bundle.score_json or {}) if isinstance(bundle.score_json, dict) else {},
        metadata=dict(bundle.metadata_json or {}) if isinstance(bundle.metadata_json, dict) else {},
        published_at=bundle.published_at.isoformat() if bundle.published_at else None,
        created_at=bundle.created_at.isoformat(),
        updated_at=bundle.updated_at.isoformat(),
    )
    return payload.model_dump(mode="json")


def list_runtime_bundles(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
) -> list[RuntimeBundle]:
    return list(
        db.scalars(
            select(RuntimeBundle)
            .where(
                and_(
                    RuntimeBundle.owner_user_id == user.id,
                    RuntimeBundle.workspace_id == workspace.id,
                )
            )
            .order_by(RuntimeBundle.updated_at.desc(), RuntimeBundle.created_at.desc())
        )
    )


def get_runtime_bundle_for_workspace(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    bundle_id: str,
) -> RuntimeBundle:
    bundle = db.scalar(
        select(RuntimeBundle).where(
            and_(
                RuntimeBundle.id == bundle_id,
                RuntimeBundle.owner_user_id == user.id,
                RuntimeBundle.workspace_id == workspace.id,
            )
        )
    )
    if bundle is None:
        raise FileNotFoundError("Runtime bundle not found.")
    return bundle


def resolve_active_runtime_bundle(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    profile: RuntimeProfile | None = None,
) -> RuntimeBundle | None:
    bundle_id = str(getattr(profile, "active_bundle_id", "") or "").strip()
    if bundle_id:
        try:
            return get_runtime_bundle_for_workspace(db, user=user, workspace=workspace, bundle_id=bundle_id)
        except FileNotFoundError:
            pass
    return db.scalar(
        select(RuntimeBundle)
        .where(
            and_(
                RuntimeBundle.owner_user_id == user.id,
                RuntimeBundle.workspace_id == workspace.id,
                RuntimeBundle.status == "published",
            )
        )
        .order_by(RuntimeBundle.published_at.desc(), RuntimeBundle.updated_at.desc())
    )


def create_runtime_bundle(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    name: str,
    prompts: dict[str, Any] | None = None,
    rubric: dict[str, Any] | None = None,
    routing_policy: dict[str, Any] | None = None,
    review_thresholds: dict[str, Any] | None = None,
    delivery_thresholds: dict[str, Any] | None = None,
    eval_baseline: dict[str, Any] | None = None,
    score: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    status: str = "draft",
    version: str | None = None,
) -> RuntimeBundle:
    bundle = RuntimeBundle(
        workspace_id=workspace.id,
        owner_user_id=user.id,
        name=name.strip() or "Runtime Bundle",
        version=(version or f"rb-{utc_timestamp_slug()}").strip(),
        status=status.strip() or "draft",
        prompts_json=dict(prompts or _bundle_prompt_defaults()),
        rubric_json=dict(rubric or {}),
        routing_policy_json=dict(routing_policy or _default_routing_policy()),
        review_thresholds_json=dict(review_thresholds or _default_review_thresholds()),
        delivery_thresholds_json=dict(delivery_thresholds or _default_delivery_thresholds()),
        eval_baseline_json=dict(eval_baseline or {}),
        score_json=dict(score or {}),
        metadata_json=dict(metadata or {}),
    )
    db.add(bundle)
    db.flush()
    return bundle


def update_runtime_bundle_score(
    db: Session,
    *,
    bundle: RuntimeBundle,
    score_snapshot: dict[str, Any],
    eval_baseline: dict[str, Any] | None = None,
) -> RuntimeBundle:
    bundle.score_json = dict(score_snapshot or {})
    if eval_baseline is not None:
        bundle.eval_baseline_json = dict(eval_baseline or {})
    db.flush()
    return bundle


def publish_runtime_bundle(
    db: Session,
    *,
    bundle: RuntimeBundle,
) -> RuntimeBundle:
    score_snapshot = dict(bundle.score_json or {}) if isinstance(bundle.score_json, dict) else {}
    if not bool(score_snapshot.get("deliverable")) or int(score_snapshot.get("total_score") or 0) != 500:
        raise ValueError("Only a 500/500 runtime bundle can be published.")
    bundle.status = "published"
    bundle.published_at = _utc_now()
    db.flush()
    return bundle


def _default_local_integration(db: Session, *, user: User) -> IntegrationCredential | None:
    integrations = list(
        db.scalars(
            select(IntegrationCredential)
            .where(
                and_(
                    IntegrationCredential.owner_user_id == user.id,
                    IntegrationCredential.category == "llm",
                )
            )
            .order_by(IntegrationCredential.is_default.desc(), IntegrationCredential.updated_at.desc())
        )
    )
    for integration in integrations:
        if is_local_provider_kind(integration.kind):
            return integration
    return None


def ensure_runtime_profile_for_bundle_apply(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    runtime_profile_id: str | None = None,
) -> RuntimeProfile:
    if runtime_profile_id:
        return get_runtime_profile_for_workspace(db, user=user, workspace=workspace, runtime_profile_id=runtime_profile_id)
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
    integration = _default_local_integration(db, user=user)
    if integration is None:
        raise ValueError("A default local runtime integration is required before applying a runtime bundle.")
    profile = create_runtime_profile(
        db,
        user=user,
        workspace=workspace,
        request=RuntimeProfileRequest(
            name="Default Runtime Profile",
            description="Auto-created profile for the active local runtime bundle.",
            is_default=True,
            bindings=[
                StageProviderBinding(stage=stage, integration_id=integration.id)
                for stage in ("planner", "researcher", "writer", "reviewer")
            ],
        ),
    )
    return profile


def apply_runtime_bundle(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    bundle: RuntimeBundle,
    runtime_profile_id: str | None = None,
) -> RuntimeProfile:
    if bundle.status != "published":
        raise ValueError("Only a published runtime bundle can be applied.")
    profile = ensure_runtime_profile_for_bundle_apply(
        db,
        user=user,
        workspace=workspace,
        runtime_profile_id=runtime_profile_id,
    )
    profile.active_bundle_id = bundle.id
    metadata = dict(profile.metadata_json or {}) if isinstance(profile.metadata_json, dict) else {}
    metadata["bundle_provenance"] = {
        "bundle_id": bundle.id,
        "bundle_version": bundle.version,
        "applied_at": _utc_now().isoformat(),
    }
    profile.metadata_json = metadata
    db.flush()
    return profile


def record_runtime_profile_health(
    db: Session,
    *,
    settings,
    user: User,
    workspace: Workspace,
    profile: RuntimeProfile,
) -> dict[str, Any]:
    gateway = ProviderGateway(settings)
    providers: list[dict[str, Any]] = []
    seen_integration_ids: set[str] = set()
    bindings_payload = profile.bindings_json.get("bindings", []) if isinstance(profile.bindings_json, dict) else []
    for item in bindings_payload:
        if not isinstance(item, dict):
            continue
        integration_id = str(item.get("integration_id") or "").strip()
        if not integration_id or integration_id in seen_integration_ids:
            continue
        seen_integration_ids.add(integration_id)
        integration = db.scalar(
            select(IntegrationCredential).where(
                and_(
                    IntegrationCredential.id == integration_id,
                    IntegrationCredential.owner_user_id == user.id,
                )
            )
        )
        if integration is None:
            providers.append(
                {
                    "integration_id": integration_id,
                    "status": "error",
                    "reason": "Integration not found.",
                }
            )
            continue
        result = gateway.test_integration(integration)
        providers.append(
            {
                "integration_id": integration.id,
                "label": integration.label,
                "kind": integration.kind,
                "model": integration.model,
                **result,
            }
        )
    local_runtime = collect_local_runtime_health(settings, db=db, user=user, workspace=workspace)
    provider_status = {item.get("kind", ""): item.get("status") == "ok" for item in providers if item.get("kind")}
    required_targets = {
        "ollama": bool(provider_status.get("ollama")) and bool(local_runtime["ollama"]["model_present"]),
        "vllm": bool(provider_status.get("vllm")) and bool(local_runtime["vllm"]["model_present"]),
    }
    blocker_messages: list[str] = list(local_runtime.get("quality_gate_blockers") or [])
    for provider in providers:
        if provider.get("status") != "ok":
            label = str(provider.get("kind") or provider.get("label") or "provider").strip()
            reason = str(provider.get("reason") or "Provider request failed.").strip()
            blocker_messages.append(f"{label}:{reason}")
    snapshot = {
        "checked_at": _utc_now().isoformat(),
        "providers": providers,
        "required_targets": required_targets,
        "vllm_source": local_runtime["vllm"].get("install_source", "official"),
        "vllm_python": local_runtime["vllm"].get("python_path", ""),
        "blocking_reason": "; ".join(dict.fromkeys(item for item in blocker_messages if item)),
        "local_runtime": local_runtime,
        "status": "ok" if all(required_targets.values()) and not blocker_messages else "error",
    }
    profile.health_json = snapshot
    db.flush()
    return snapshot


def bundle_instruction_overrides(bundle: RuntimeBundle | None) -> dict[str, str]:
    if bundle is None or not isinstance(bundle.prompts_json, dict):
        return {}
    return {
        key: str(value or "").strip()
        for key, value in bundle.prompts_json.items()
        if str(value or "").strip()
    }


def bundle_review_thresholds(bundle: RuntimeBundle | None) -> dict[str, Any]:
    if bundle is None or not isinstance(bundle.review_thresholds_json, dict):
        return _default_review_thresholds()
    payload = dict(_default_review_thresholds())
    payload.update(dict(bundle.review_thresholds_json or {}))
    return payload
