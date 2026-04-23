from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from research_agent.cli import app as cli_app
from research_agent.config import get_settings


runner = CliRunner()


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
    def fake_get(url: str, timeout: int = 20, allow_redirects: bool = False):
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

    monkeypatch.setattr("research_agent.cli.requests.get", fake_get)
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
