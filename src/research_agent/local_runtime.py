from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .config import Settings
from .entities import AgentRun, IntegrationCredential, RuntimeBundle, RuntimeProfile, User, Workspace
from .provider_catalog import is_local_provider_kind


LOCAL_RUNTIME_DIRNAME = "local-runtime"
LOCAL_RUNTIME_APP_PORT = 8000
LOCAL_RUNTIME_OLLAMA_PORT = 11434
LOCAL_RUNTIME_VLLM_PORT = 8010
LOCAL_RUNTIME_OLLAMA_LABEL = "Local Ollama"
LOCAL_RUNTIME_VLLM_LABEL = "Local vLLM"
LOCAL_RUNTIME_PROFILE_NAME = "Local Runtime Profile"
LOCAL_RUNTIME_BUNDLE_NAME = "Local Runtime Bootstrap Bundle"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def local_runtime_dir(settings: Settings) -> Path:
    path = settings.storage_dir / "runtime" / LOCAL_RUNTIME_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def bootstrap_manifest_path(settings: Settings) -> Path:
    return local_runtime_dir(settings) / "bootstrap_manifest.json"


def local_runtime_pid_dir(settings: Settings) -> Path:
    path = local_runtime_dir(settings) / "pids"
    path.mkdir(parents=True, exist_ok=True)
    return path


def local_runtime_log_dir(settings: Settings) -> Path:
    path = local_runtime_dir(settings) / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def local_runtime_pid_path(settings: Settings, name: str) -> Path:
    return local_runtime_pid_dir(settings) / f"{name}.pid"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def read_bootstrap_manifest(settings: Settings) -> dict[str, Any]:
    return _read_json(bootstrap_manifest_path(settings))


def _run_command(args: list[str], *, timeout: int = 20) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout,
            check=False,
        )
    except Exception:
        return None


def _command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def _base_root_from_openai_url(base_url: str, *, default_port: int) -> str:
    normalized = (base_url or "").strip() or f"http://127.0.0.1:{default_port}/v1"
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return normalized.rstrip("/")


def _port_from_url(base_url: str, *, default_port: int) -> tuple[str, int]:
    parsed = urlsplit((base_url or "").strip() or f"http://127.0.0.1:{default_port}/v1")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or default_port
    return host, port


def is_port_open(host: str, port: int, *, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_json(url: str, *, timeout: int = 5) -> tuple[bool, dict[str, Any] | list[Any], str]:
    try:
        response = requests.get(url, timeout=timeout)
    except requests.RequestException as exc:
        return False, {}, str(exc)
    if response.status_code >= 400:
        return False, {}, f"HTTP {response.status_code}"
    try:
        payload = response.json()
    except ValueError:
        return False, {}, "non_json_response"
    return True, payload, ""


def _python_version(python_path: str) -> str:
    completed = _run_command([python_path, "--version"], timeout=10)
    if completed is None:
        return ""
    version_text = " ".join(
        part.strip()
        for part in [completed.stdout.strip(), completed.stderr.strip()]
        if part.strip()
    )
    return version_text.strip()


def _process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _pid_file_status(path: Path) -> tuple[bool, int | None]:
    if not path.exists():
        return False, None
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except Exception:
        return False, None
    return _process_running(pid), pid


def _bool_text(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return "yes" if value else "no"


def _port_snapshot(host: str, port: int) -> dict[str, Any]:
    listening = is_port_open(host, port)
    return {
        "host": host,
        "port": port,
        "listening": listening,
        "status": "occupied" if listening else "free",
    }


def _probe_ollama(settings: Settings) -> dict[str, Any]:
    host, port = _port_from_url(settings.ollama_base_url, default_port=LOCAL_RUNTIME_OLLAMA_PORT)
    port_info = _port_snapshot(host, port)
    installed = _command_exists("ollama")
    version = ""
    if installed:
        completed = _run_command(["ollama", "--version"], timeout=10)
        if completed is not None:
            version = " ".join(
                part.strip()
                for part in [completed.stdout.strip(), completed.stderr.strip()]
                if part.strip()
            ).strip()
    ok, payload, reason = _http_json(
        f"{_base_root_from_openai_url(settings.ollama_base_url, default_port=LOCAL_RUNTIME_OLLAMA_PORT)}/api/tags"
    )
    models = payload.get("models", []) if isinstance(payload, dict) else []
    model_names = [
        str(item.get("name") or item.get("model") or "").strip()
        for item in models
        if isinstance(item, dict)
    ]
    model_present = settings.ollama_model in model_names
    failure_code = ""
    if not installed:
        failure_code = "not_installed"
    elif not ok and port_info["listening"]:
        failure_code = "port_conflict"
    elif not ok:
        failure_code = "not_running"
    elif not model_present:
        failure_code = "model_missing"
    return {
        "label": "ollama",
        "installed": installed,
        "version": version,
        "host": host,
        "port": port,
        "running": ok,
        "model": settings.ollama_model,
        "model_present": model_present if ok else False,
        "models": model_names,
        "failure_code": failure_code,
        "reason": reason,
        "base_url": settings.ollama_base_url,
        "port_status": port_info,
    }


def _probe_vllm(settings: Settings, manifest: dict[str, Any]) -> dict[str, Any]:
    host, port = _port_from_url(settings.vllm_base_url, default_port=LOCAL_RUNTIME_VLLM_PORT)
    port_info = _port_snapshot(host, port)
    python_path = str(Path(settings.vllm_python).expanduser())
    python_present = Path(python_path).exists()
    python_version = _python_version(python_path) if python_present else ""
    install_source = str(manifest.get("install_source") or "").strip() or "official"
    ok, payload, reason = _http_json(f"{settings.vllm_base_url.rstrip('/')}/models")
    models = payload.get("data", []) if isinstance(payload, dict) else []
    model_names = [
        str(item.get("id") or "").strip()
        for item in models
        if isinstance(item, dict)
    ]
    model_present = settings.vllm_model in model_names
    failure_code = ""
    if not python_present:
        failure_code = "not_installed"
    elif python_version and not python_version.startswith("Python 3.12"):
        failure_code = "python_mismatch"
    elif not ok and port_info["listening"]:
        failure_code = "port_conflict"
    elif not ok:
        failure_code = "not_running"
    elif not model_present:
        failure_code = "model_missing"
    install_note = "community_build_required" if install_source == "community_windows" else ""
    return {
        "label": "vllm",
        "python_path": python_path,
        "python_present": python_present,
        "python_version": python_version,
        "install_source": install_source,
        "install_note": install_note,
        "host": host,
        "port": port,
        "running": ok,
        "model": settings.vllm_model,
        "model_present": model_present if ok else False,
        "models": model_names,
        "failure_code": failure_code,
        "reason": reason,
        "base_url": settings.vllm_base_url,
        "api_key": settings.vllm_api_key,
        "port_status": port_info,
    }


def _probe_app(settings: Settings) -> dict[str, Any]:
    base_url = settings.public_base_url.strip() or f"http://127.0.0.1:{LOCAL_RUNTIME_APP_PORT}"
    host, port = _port_from_url(base_url, default_port=LOCAL_RUNTIME_APP_PORT)
    port_info = _port_snapshot(host, port)
    ok, _, reason = _http_json(f"{base_url.rstrip('/')}/api/bootstrap")
    failure_code = ""
    if not ok and port_info["listening"]:
        failure_code = "port_conflict"
    elif not ok:
        failure_code = "not_running"
    return {
        "label": "app",
        "base_url": base_url,
        "host": host,
        "port": port,
        "running": ok,
        "failure_code": failure_code,
        "reason": reason,
        "port_status": port_info,
    }


def _probe_worker(settings: Settings, db: Session | None = None) -> dict[str, Any]:
    pid_path = local_runtime_pid_path(settings, "worker")
    pid_running, pid = _pid_file_status(pid_path)
    heartbeat_running = False
    heartbeat_worker_id = ""
    if db is not None:
        threshold = _utc_now() - timedelta(minutes=2)
        latest_run = db.scalar(
            select(AgentRun)
            .where(
                and_(
                    AgentRun.queue_status == "claimed",
                    AgentRun.worker_heartbeat_at.is_not(None),
                    AgentRun.worker_heartbeat_at >= threshold,
                )
            )
            .order_by(AgentRun.worker_heartbeat_at.desc())
        )
        if latest_run is not None:
            heartbeat_running = True
            heartbeat_worker_id = str(latest_run.worker_id or "")
    running = pid_running or heartbeat_running
    failure_code = "" if running else "not_running"
    return {
        "running": running,
        "pid_file": str(pid_path),
        "pid": pid,
        "source": "pid_file" if pid_running else ("db_heartbeat" if heartbeat_running else "none"),
        "worker_id": heartbeat_worker_id,
        "failure_code": failure_code,
    }


def _runtime_context_snapshot(
    db: Session | None,
    *,
    user: User | None,
    workspace: Workspace | None,
) -> dict[str, Any]:
    if db is None or user is None or workspace is None:
        return {
            "context_provided": False,
            "default_local_integration_present": None,
            "default_runtime_profile_present": None,
            "active_runtime_bundle_present": None,
            "default_runtime_profile_id": "",
            "active_runtime_bundle_id": "",
            "quality_gate_blockers": [],
        }
    default_local_integration = db.scalar(
        select(IntegrationCredential).where(
            and_(
                IntegrationCredential.owner_user_id == user.id,
                IntegrationCredential.category == "llm",
                IntegrationCredential.is_default.is_(True),
            )
        )
    )
    local_integration_present = bool(
        default_local_integration is not None and is_local_provider_kind(default_local_integration.kind)
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
    bundle = None
    if profile is not None and getattr(profile, "active_bundle_id", None):
        bundle = db.get(RuntimeBundle, profile.active_bundle_id)
    blockers: list[str] = []
    if not local_integration_present:
        blockers.append("default_local_integration_missing")
    if profile is None:
        blockers.append("runtime_profile_missing")
    if profile is not None and bundle is None:
        blockers.append("bundle_missing")
    return {
        "context_provided": True,
        "default_local_integration_present": local_integration_present,
        "default_runtime_profile_present": profile is not None,
        "active_runtime_bundle_present": bundle is not None,
        "default_runtime_profile_id": str(profile.id if profile is not None else ""),
        "active_runtime_bundle_id": str(bundle.id if bundle is not None else ""),
        "quality_gate_blockers": blockers,
    }


def collect_local_runtime_health(
    settings: Settings,
    *,
    db: Session | None = None,
    user: User | None = None,
    workspace: Workspace | None = None,
) -> dict[str, Any]:
    manifest = read_bootstrap_manifest(settings)
    manifest_blockers = [
        str(item).strip()
        for item in (manifest.get("blockers") or [])
        if str(item).strip()
    ]
    ollama = _probe_ollama(settings)
    vllm = _probe_vllm(settings, manifest)
    app = _probe_app(settings)
    worker = _probe_worker(settings, db=db)
    runtime = _runtime_context_snapshot(db, user=user, workspace=workspace)

    blockers: list[str] = []
    for item in (ollama, vllm, app):
        failure_code = str(item.get("failure_code") or "").strip()
        if failure_code:
            blockers.append(f"{item['label']}:{failure_code}")
    if str(vllm.get("install_note") or "").strip():
        blockers.append(str(vllm["install_note"]))
    if not worker["running"]:
        blockers.append(f"worker:{worker['failure_code']}")
    blockers.extend(runtime["quality_gate_blockers"])
    blockers.extend(manifest_blockers)
    blockers = list(dict.fromkeys(item for item in blockers if str(item).strip()))
    blocking_reason = "; ".join(blockers)

    return {
        "checked_at": _utc_now().isoformat(),
        "manifest_path": str(bootstrap_manifest_path(settings)),
        "manifest": manifest,
        "manifest_blockers": manifest_blockers,
        "app": app,
        "ollama": ollama,
        "vllm": vllm,
        "ports": {
            "app": app["port_status"],
            "ollama": ollama["port_status"],
            "vllm": vllm["port_status"],
        },
        "worker": worker,
        "runtime": runtime,
        "quality_gate_blockers": blockers,
        "blocking_reason": blocking_reason,
    }


def format_local_runtime_doctor_lines(snapshot: dict[str, Any]) -> list[str]:
    runtime = dict(snapshot.get("runtime") or {})
    app = dict(snapshot.get("app") or {})
    ollama = dict(snapshot.get("ollama") or {})
    vllm = dict(snapshot.get("vllm") or {})
    worker = dict(snapshot.get("worker") or {})
    ports = dict(snapshot.get("ports") or {})
    manifest_blockers = list(snapshot.get("manifest_blockers") or [])
    return [
        "Local Runtime:",
        f"  ERP app running: {_bool_text(app.get('running'))} ({app.get('base_url', '')})"
        + (f" [{app.get('failure_code')}]" if app.get("failure_code") else ""),
        f"  Ollama installed: {_bool_text(ollama.get('installed'))}",
        f"  Ollama running: {_bool_text(ollama.get('running'))}"
        + (f" [{ollama.get('failure_code')}]" if ollama.get("failure_code") else ""),
        f"  Ollama model present: {_bool_text(ollama.get('model_present'))} ({ollama.get('model', '')})",
        f"  vLLM python present: {_bool_text(vllm.get('python_present'))} ({vllm.get('python_path', '')})",
        f"  vLLM install source: {vllm.get('install_source', 'unknown')}",
        f"  vLLM running: {_bool_text(vllm.get('running'))}"
        + (f" [{vllm.get('failure_code')}]" if vllm.get("failure_code") else ""),
        f"  vLLM model present: {_bool_text(vllm.get('model_present'))} ({vllm.get('model', '')})",
        f"  Ports: 8000={ports.get('app', {}).get('status', 'unknown')}, "
        f"11434={ports.get('ollama', {}).get('status', 'unknown')}, "
        f"8010={ports.get('vllm', {}).get('status', 'unknown')}",
        f"  Worker running: {_bool_text(worker.get('running'))}",
        f"  Default local integration present: {_bool_text(runtime.get('default_local_integration_present'))}",
        f"  Default runtime profile present: {_bool_text(runtime.get('default_runtime_profile_present'))}",
        f"  Active runtime bundle present: {_bool_text(runtime.get('active_runtime_bundle_present'))}",
        f"  Bootstrap blockers: {', '.join(manifest_blockers) or 'none'}",
        f"  Quality gate blockers: {', '.join(snapshot.get('quality_gate_blockers') or []) or 'none'}",
    ]
