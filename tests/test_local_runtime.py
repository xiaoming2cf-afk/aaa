from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from research_agent.cli import app as cli_app
from research_agent.config import get_settings


runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_env_defaults_do_not_expose_runtime_model_endpoints(monkeypatch):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("VLLM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)

    cache_clear = getattr(get_settings, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()
    settings = get_settings()
    if callable(cache_clear):
        cache_clear()

    assert settings.model
    assert settings.openai_api_key == ""
    assert not hasattr(settings, "ollama_base_url")
    assert not hasattr(settings, "vllm_base_url")


def test_doctor_reports_only_business_platform_checks():
    result = runner.invoke(cli_app, ["doctor"])

    assert result.exit_code == 0, result.stdout
    assert "Platform Doctor" in result.stdout
    assert "OpenAlex" in result.stdout
    assert "World Bank API" in result.stdout
    assert "Local Runtime" not in result.stdout
    assert "Ollama" not in result.stdout
    assert "vLLM" not in result.stdout


def test_production_entrypoints_do_not_import_runtime_modules():
    repo_root = Path(__file__).resolve().parents[1]
    targets = [
        repo_root / "src" / "research_agent" / "cli.py",
        repo_root / "src" / "research_agent" / "service.py",
        repo_root / "src" / "research_agent" / "webapp.py",
        repo_root / "src" / "research_agent" / "platform_research.py",
    ]
    forbidden = [
        ".local_runtime",
        ".runtime_bundles",
        ".runtime_profiles",
        ".runtime_provider",
        ".provider_gateway",
    ]

    for path in targets:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path.name} should not import {token}"


def test_render_contract_builds_spa_without_runtime_model_variables():
    repo_root = Path(__file__).resolve().parents[1]
    render_yaml = (repo_root / "render.yaml").read_text(encoding="utf-8")

    assert "frontend-spa" in render_yaml
    assert "npm run build" in render_yaml
    assert "RESEARCH_AGENT_MODEL" not in render_yaml
    assert "OPENAI_API_KEY" not in render_yaml
    assert "DATA_LAB_AGENT_ENABLED" in render_yaml
    assert "AGENT_MATH_MODE" in render_yaml
    assert "AGENT_MATH_OVERRIDE_MARGIN" in render_yaml


def test_smoke_deploy_checks_expected_routes(monkeypatch, tmp_path):
    def fake_get(self, url: str, timeout: int = 20, allow_redirects: bool = False):
        del self
        if url.endswith("/api/auth/me"):
            return SimpleNamespace(
                status_code=401,
                headers={},
                text='{"detail":"Not authenticated"}',
                json=lambda: {"detail": "Not authenticated"},
            )
        if url.endswith("/api/health"):
            return SimpleNamespace(
                status_code=200,
                headers={},
                text='{"status":"ok"}',
                json=lambda: {"status": "ok"},
            )
        if url.endswith("/provider-center"):
            return SimpleNamespace(
                status_code=200,
                headers={},
                text="Provider Center is not part of the current product scope.",
                json=lambda: {},
            )
        return SimpleNamespace(
            status_code=307,
            headers={"location": "/"},
            text="",
            json=lambda: {},
        )

    monkeypatch.setattr("research_agent.cli.requests.Session.get", fake_get)
    output_path = tmp_path / "deploy-smoke.json"

    result = runner.invoke(
        cli_app,
        ["smoke-deploy", "--base-url", "https://economic-research-web.onrender.com", "--output", str(output_path)],
    )

    assert result.exit_code == 0, result.stdout
    assert "Deploy Smoke" in result.stdout
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert any(item["path"] == "/app/data-lab-agent" for item in payload["checks"])
    for expected in ("/api/auth/me", "/app", "/app/quality", "/app/data-lab-agent", "/provider-center"):
        assert expected in payload["required_paths"]


def test_smoke_deploy_rejects_source_entry_shell(monkeypatch, tmp_path):
    def fake_get(self, url: str, timeout: int = 20, allow_redirects: bool = False):
        del self, timeout, allow_redirects
        if url.endswith("/api/auth/me"):
            return SimpleNamespace(
                status_code=401,
                headers={},
                text='{"detail":"Not authenticated"}',
                json=lambda: {"detail": "Not authenticated"},
            )
        if url.endswith("/api/health"):
            return SimpleNamespace(
                status_code=200,
                headers={},
                text='{"status":"ok"}',
                json=lambda: {"status": "ok"},
            )
        if url.endswith("/provider-center"):
            return SimpleNamespace(
                status_code=200,
                headers={},
                text="Provider Center is not part of the current product scope.",
                json=lambda: {},
            )
        if url.endswith("/app/data-lab-agent"):
            return SimpleNamespace(
                status_code=200,
                headers={},
                text='<script type="module" src="/src/main.tsx"></script>',
                json=lambda: {},
            )
        return SimpleNamespace(
            status_code=307,
            headers={"location": "/"},
            text="",
            json=lambda: {},
        )

    monkeypatch.setattr("research_agent.cli.requests.Session.get", fake_get)
    output_path = tmp_path / "deploy-smoke-source-entry.json"

    result = runner.invoke(
        cli_app,
        ["smoke-deploy", "--base-url", "https://economic-research-web.onrender.com", "--output", str(output_path)],
    )

    assert result.exit_code == 1, result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    failing = next(item for item in payload["checks"] if item["path"] == "/app/data-lab-agent")
    assert failing["passed"] is False
    assert failing["key"] == "spa_route_uses_built_assets"
    assert "SPA shell still references /src/main.tsx" in failing["detail"]


def test_smoke_deploy_accepts_quality_scorecard_fail_closed(monkeypatch, tmp_path):
    auth_me_calls = {"count": 0}

    def fake_get(self, url: str, timeout: int = 20, allow_redirects: bool = False):
        del timeout, allow_redirects
        if url.endswith("/api/auth/me"):
            auth_me_calls["count"] += 1
            if auth_me_calls["count"] == 1:
                return SimpleNamespace(
                    status_code=401,
                    headers={},
                    text='{"detail":"Not authenticated"}',
                    json=lambda: {"detail": "Not authenticated"},
                )
            return SimpleNamespace(
                status_code=200,
                headers={},
                text='{"user":{"email":"smoke@example.invalid"}}',
                json=lambda: {"user": {"email": "smoke@example.invalid"}},
            )
        if url.endswith("/api/health"):
            return SimpleNamespace(
                status_code=200,
                headers={},
                text='{"status":"ok"}',
                json=lambda: {"status": "ok"},
            )
        if url.endswith("/provider-center"):
            return SimpleNamespace(
                status_code=200,
                headers={},
                text="Provider Center is not part of the current product scope.",
                json=lambda: {},
            )
        if url.endswith("/quality/scorecard"):
            return SimpleNamespace(
                status_code=200,
                headers={},
                text='{"engineering_gate":{"passed":false,"source":"missing"}}',
                json=lambda: {"engineering_gate": {"passed": False, "source": "missing"}},
            )
        return SimpleNamespace(
            status_code=307,
            headers={"location": "/"},
            text="",
            json=lambda: {},
        )

    def fake_post(self, url: str, *args, **kwargs):
        del args, kwargs
        if url.endswith("/api/auth/register"):
            self.cookies.set("erp_session_token", "token")
            return SimpleNamespace(status_code=200, headers={}, text='{}', json=lambda: {})
        if url.endswith("/api/workspaces"):
            return SimpleNamespace(
                status_code=200,
                headers={},
                text='{"workspace":{"id":"workspace-1"}}',
                json=lambda: {"workspace": {"id": "workspace-1"}},
            )
        if url.endswith("/assets/upload"):
            return SimpleNamespace(
                status_code=200,
                headers={},
                text='{"asset":{"id":"asset-1"}}',
                json=lambda: {"asset": {"id": "asset-1"}},
            )
        return SimpleNamespace(status_code=404, headers={}, text="missing", json=lambda: {})

    monkeypatch.setattr("research_agent.cli.requests.Session.get", fake_get)
    monkeypatch.setattr("research_agent.cli.requests.Session.post", fake_post)
    output_path = tmp_path / "deploy-smoke-fail-closed.json"

    result = runner.invoke(
        cli_app,
        [
            "smoke-deploy",
            "--base-url",
            "https://economic-research-web.onrender.com",
            "--deep",
            "--register",
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    quality = next(item for item in payload["checks"] if item.get("key") == "quality_scorecard_accessible")
    assert quality["passed"] is True
    assert quality["detail"] == "missing"


def test_render_deploy_missing_credentials_report_is_actionable(monkeypatch):
    module = _load_script_module("verify_render_deploy_test", "scripts/verify_render_deploy.py")
    monkeypatch.delenv("RENDER_DEPLOY_HOOK", raising=False)
    monkeypatch.delenv("RENDER_API_KEY", raising=False)
    monkeypatch.delenv("RENDER_SERVICE_ID", raising=False)

    report = module.trigger_render_deploy(commit_sha="abc123")

    assert report["passed"] is False
    assert report["commit_sha"] == "abc123"
    assert report["credentials"]["missing_for_deploy_hook"] == ["RENDER_DEPLOY_HOOK"]
    assert report["credentials"]["missing_for_render_api"] == ["RENDER_API_KEY", "RENDER_SERVICE_ID"]
    assert "Configure either RENDER_DEPLOY_HOOK" in report["remediation"]


def test_render_deploy_promotion_requires_base_url_and_deep_smoke(tmp_path, monkeypatch):
    module = _load_script_module("verify_render_deploy_promotion_guard_test", "scripts/verify_render_deploy.py")
    output_path = tmp_path / "render-deploy.json"

    def fail_trigger(*args, **kwargs):
        raise AssertionError("Render deploy must not be triggered before promotion smoke requirements pass")

    monkeypatch.setattr(module, "trigger_render_deploy", fail_trigger)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_render_deploy.py",
            "--commit",
            "abc123",
            "--output",
            str(output_path),
        ],
    )

    exit_code = module.main()

    assert exit_code == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["passed"] is False
    assert payload["deploy"]["status"] == "not_triggered"
    assert payload["promotion"]["detail"]["missing"] == ["base_url", "deep_smoke"]
    assert "--base-url" in payload["promotion"]["detail"]["required_flags"]


def test_engineering_gate_artifact_fails_when_dist_shell_uses_source_entry(tmp_path, monkeypatch):
    module = _load_script_module("write_engineering_gate_artifact_test", "scripts/write_engineering_gate_artifact.py")
    repo_root = tmp_path / "repo"
    dist = repo_root / "frontend-spa" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text('<script type="module" src="/src/main.tsx"></script>', encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", repo_root)

    artifact = module.build_artifact(commit_sha="abc123", source="test")

    assert artifact["passed"] is False
    failing = next(check for check in artifact["checks"] if check["key"] == "spa_shell_uses_built_assets")
    assert failing["passed"] is False
    assert "/src/main.tsx" in failing["detail"]


def test_engineering_gate_artifact_contains_commit_and_critical_gates(tmp_path, monkeypatch):
    module = _load_script_module("write_engineering_gate_artifact_success_test", "scripts/write_engineering_gate_artifact.py")
    repo_root = tmp_path / "repo"
    dist = repo_root / "frontend-spa" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text('<script type="module" src="/app/assets/index-abcd.js"></script>', encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", repo_root)

    artifact = module.build_artifact(commit_sha="abc123", source="test")

    assert artifact["passed"] is True
    assert artifact["commit_sha"] == "abc123"
    keys = {check["key"] for check in artifact["checks"]}
    for expected in (
        "repo_hygiene_clean",
        "backend_tests_green",
        "frontend_tests_green",
        "frontend_build_green",
        "spa_shell_uses_built_assets",
        "agent_quality_gate_green",
        "model_engine_comparison_green",
    ):
        assert expected in keys


def test_deploy_artifact_verifier_accepts_matching_green_artifacts(tmp_path):
    module = _load_script_module("verify_deploy_artifacts_success_test", "scripts/verify_deploy_artifacts.py")
    commit_sha = "abc123def456"
    engineering_gate = tmp_path / f"engineering-gate.{commit_sha}.json"
    engineering_gate.write_text(
        json.dumps(
            {
                "artifact_schema": "engineering-gate.v1",
                "commit_sha": commit_sha,
                "passed": True,
                "checks": [{"key": "backend_tests_green", "passed": True}],
            }
        ),
        encoding="utf-8",
    )
    render_deploy = tmp_path / f"render-deploy.{commit_sha}.json"
    render_deploy.write_text(
        json.dumps(
            {
                "commit_sha": commit_sha,
                "passed": True,
                "deploy": {"passed": True, "commit_sha": commit_sha},
                "smoke": {"passed": True},
            }
        ),
        encoding="utf-8",
    )

    report = module.verify_artifacts(commit_sha=commit_sha, engineering_gate=engineering_gate, render_deploy=render_deploy)

    assert report["passed"] is True
    assert report["failures"] == []


def test_deploy_artifact_verifier_blocks_commit_mismatch_and_failed_gate(tmp_path):
    module = _load_script_module("verify_deploy_artifacts_blocked_test", "scripts/verify_deploy_artifacts.py")
    commit_sha = "abc123def456"
    engineering_gate = tmp_path / "engineering-gate.wrong.json"
    engineering_gate.write_text(
        json.dumps(
            {
                "artifact_schema": "engineering-gate.v1",
                "commit_sha": "wrong",
                "passed": False,
                "checks": [{"key": "frontend_build_green", "passed": False, "detail": "failed"}],
            }
        ),
        encoding="utf-8",
    )

    report = module.verify_artifacts(commit_sha=commit_sha, engineering_gate=engineering_gate)

    assert report["passed"] is False
    failure_keys = {failure["key"] for failure in report["failures"]}
    assert "engineering_gate_commit_match" in failure_keys
    assert "engineering_gate_filename_commit_match" in failure_keys
    assert "engineering_gate_passed" in failure_keys


def test_deploy_artifact_verifier_requires_exact_commit_bound_filenames(tmp_path):
    module = _load_script_module("verify_deploy_artifacts_filename_test", "scripts/verify_deploy_artifacts.py")
    commit_sha = "abc123def456"
    engineering_gate = tmp_path / f"engineering-gate.prefix-{commit_sha}-suffix.json"
    engineering_gate.write_text(
        json.dumps(
            {
                "artifact_schema": "engineering-gate.v1",
                "commit_sha": commit_sha,
                "passed": True,
                "checks": [{"key": "backend_tests_green", "passed": True}],
            }
        ),
        encoding="utf-8",
    )

    report = module.verify_artifacts(commit_sha=commit_sha, engineering_gate=engineering_gate)

    assert report["passed"] is False
    assert {failure["key"] for failure in report["failures"]} == {"engineering_gate_filename_commit_match"}


def test_deploy_artifact_verifier_requires_render_subreports_green(tmp_path):
    module = _load_script_module("verify_deploy_artifacts_render_subreports_test", "scripts/verify_deploy_artifacts.py")
    commit_sha = "abc123def456"
    engineering_gate = tmp_path / f"engineering-gate.{commit_sha}.json"
    engineering_gate.write_text(
        json.dumps(
            {
                "artifact_schema": "engineering-gate.v1",
                "commit_sha": commit_sha,
                "passed": True,
                "checks": [{"key": "backend_tests_green", "passed": True}],
            }
        ),
        encoding="utf-8",
    )
    render_deploy = tmp_path / f"render-deploy.{commit_sha}.json"
    render_deploy.write_text(
        json.dumps(
            {
                "commit_sha": commit_sha,
                "passed": True,
                "deploy": {"passed": True, "commit_sha": commit_sha},
                "smoke": {"passed": False, "checks": []},
            }
        ),
        encoding="utf-8",
    )

    report = module.verify_artifacts(commit_sha=commit_sha, engineering_gate=engineering_gate, render_deploy=render_deploy)

    assert report["passed"] is False
    assert "render_deploy_passed" in {failure["key"] for failure in report["failures"]}


def test_model_upgrade_default_shards_cover_known_slow_methods():
    module = _load_script_module("verify_model_upgrade_shards_test", "scripts/verify_model_upgrade.py")

    shard_methods = ",".join(shard.get("methods", "") for shard in module._DEFAULT_VERIFICATION_SHARDS)

    assert len(module._DEFAULT_VERIFICATION_SHARDS) >= 5
    assert "country_panel" in {shard.get("groups", "") for shard in module._DEFAULT_VERIFICATION_SHARDS}
    assert "varmax" in shard_methods
    assert "discrete_allocation" in shard_methods


def test_model_upgrade_shard_json_parser_ignores_progress_lines():
    module = _load_script_module("verify_model_upgrade_json_parser_test", "scripts/verify_model_upgrade.py")

    report = module._extract_json_report(
        "[verify_model_upgrade] START varmax\n"
        "{\"status\": \"passed\", \"model_count\": 1, \"models\": []}\n"
        "non-json trailer\n"
    )

    assert report["status"] == "passed"
    assert report["model_count"] == 1
