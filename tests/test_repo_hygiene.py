from __future__ import annotations

from pathlib import Path

from research_agent.repo_hygiene import scan_repo_hygiene


def test_repo_hygiene_scans_nested_source_config_and_log_files(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "logs").mkdir()

    source_file = tmp_path / "src" / "settings.py"
    github_token = "ghp_" + "1234567890abcdef1234567890ABCDEF1234"
    source_file.write_text(
        f'GITHUB_TOKEN = "{github_token}"\n',
        encoding="utf-8",
    )
    key_file = tmp_path / "config" / "deploy.pem"
    private_key_header = "-----BEGIN " + "PRIVATE KEY-----"
    private_key_footer = "-----END " + "PRIVATE KEY-----"
    key_file.write_text(
        f"{private_key_header}\nabc123\n{private_key_footer}\n",
        encoding="utf-8",
    )
    temp_log = tmp_path / "logs" / "_tmp_access.log"
    temp_log.write_text("temporary\n", encoding="utf-8")

    issues = scan_repo_hygiene(tmp_path)

    assert any(
        item["kind"] == "secret_pattern"
        and item["label"] == "github_token"
        and item["path"] == str(source_file)
        and item["line_number"] == 1
        for item in issues
    )
    assert any(
        item["kind"] == "secret_pattern"
        and item["label"] == "private_key_block"
        and item["path"] == str(key_file)
        and item["line_number"] == 1
        for item in issues
    )
    assert any(
        item["kind"] == "temporary_workspace_artifact"
        and item["label"] == "_tmp_access.log"
        and item["path"] == str(temp_log)
        for item in issues
    )


def test_repo_hygiene_ignores_virtualenv_egg_info_and_large_files(tmp_path: Path):
    venv_file = tmp_path / ".venv" / "leaked.py"
    venv_file.parent.mkdir()
    github_token = "ghp_" + "1234567890abcdef1234567890ABCDEF1234"
    openai_key = "sk-" + "proj-" + "secretsecretsecretsecret"
    venv_file.write_text(
        f'OPENAI_API_KEY = "{openai_key}"\n',
        encoding="utf-8",
    )

    egg_info_file = tmp_path / "src" / "research_agent.egg-info" / "PKG-INFO"
    egg_info_file.parent.mkdir(parents=True)
    database_url = "postgresql://" + "user:secret@example.com/app"
    egg_info_file.write_text(
        f"DATABASE_URL={database_url}\n",
        encoding="utf-8",
    )

    oversized_log = tmp_path / "logs" / "trace.log"
    oversized_log.parent.mkdir()
    oversized_log.write_text(
        ("x" * 600_000) + github_token,
        encoding="utf-8",
    )

    issues = scan_repo_hygiene(tmp_path)

    assert issues == []


def test_repo_hygiene_still_scans_env_examples(tmp_path: Path):
    env_example = tmp_path / ".env.example"
    openai_key = "sk-" + "proj-" + "secretsecretsecretsecret"
    env_example.write_text(
        f"OPENAI_API_KEY={openai_key}\n",
        encoding="utf-8",
    )

    issues = scan_repo_hygiene(tmp_path)

    assert any(
        item["kind"] == "secret_pattern"
        and item["label"] == "openai_api_key"
        and item["path"] == str(env_example)
        for item in issues
    )


def test_repo_hygiene_reports_root_temp_directories_without_descending(tmp_path: Path):
    temp_root = tmp_path / "_tmp_buildcheck"
    site_packages = temp_root / "Lib" / "site-packages" / "pip" / "_internal" / "utils"
    site_packages.mkdir(parents=True)
    nested_file = site_packages / "temp_dir.py"
    nested_file.write_text(
        "TEMP_DIR = True\n",
        encoding="utf-8",
    )

    issues = scan_repo_hygiene(tmp_path)

    assert any(
        item["kind"] == "temporary_workspace_artifact"
        and item["label"] == "_tmp_buildcheck"
        and item["path"] == str(temp_root)
        for item in issues
    )
    assert not any(item["path"] == str(nested_file) for item in issues)


def test_ci_workflow_contains_delivery_gate_slices():
    workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
    text = workflow.read_text(encoding="utf-8")

    for expected in (
        "Backend pytest",
        "Frontend tests",
        "Frontend build",
        "frontend-dist-${{ github.sha }}",
        "Scan repository hygiene",
        "Verify agent quality gate",
        "Compare model engines",
        "Write commit-bound engineering gate artifact",
        "Verify model upgrade slow gate",
        "Trigger Render deploy and smoke check",
        "render-deploy-${{ github.sha }}",
    ):
        assert expected in text
