from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any


_SUSPICIOUS_ROOT_FILENAMES = {
    "o.value)",
    "o.value))",
    "o.value).join('",
}
_IGNORE_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "storage",
    "reports",
    "output",
    "dist",
    "build",
}
_IGNORE_DIR_SUFFIXES = {".egg-info"}
_IGNORE_FILE_NAMES = {
    ".ds_store",
    "thumbs.db",
}
_IGNORE_DIR_PATTERNS = {
    re.compile(r"^_tmp(?:$|[_-])", re.IGNORECASE),
}
_IGNORE_PATH_GLOBS = {
    "*.pyc",
    "*.pyo",
    "*.pyd",
}
_SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "database_url_secret": re.compile(r"postgres(?:ql(?:\+psycopg)?)://[^:\s]+:[^@\s]+@",
                                      re.IGNORECASE),
    "supabase_service_role": re.compile(r"sb_secret_[A-Za-z0-9._-]{10,}"),
    "openai_api_key": re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{12,}\b"),
    "anthropic_api_key": re.compile(r"\bsk-ant-[A-Za-z0-9._-]{12,}\b"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z\\-_]{20,}\b"),
    "azure_openai_key": re.compile(
        r"(?i)\b(?:azure[_-]?openai[_-]?key|openai[_-]?api[_-]?key|api[_-]?key)\b"
        r"[^=\n]{0,16}[:=]\s*['\"]?[a-f0-9]{32}\b"
    ),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "slack_token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "jwt_token": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9._-]{8,}\.[A-Za-z0-9._-]{8,}\b"),
    "private_key_block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    "session_token": re.compile(r"\berp\.session\.token=[A-Za-z0-9._-]{20,}\b"),
}
_TEMP_FILE_PATTERNS: dict[str, re.Pattern[str]] = {
    "temporary_workspace_artifact": re.compile(r"^(?:_tmp_|tmp_|temp_).+", re.IGNORECASE),
    "backup_file": re.compile(r"\.(bak|old|orig|rej|tmp)$", re.IGNORECASE),
    "editor_swap_file": re.compile(r"(^\.#.*|.*~$|.*\.sw[opx]$)", re.IGNORECASE),
    "sqlite_sidecar_file": re.compile(
        r"\.(?:sqlite-(?:wal|shm|journal)|db-(?:wal|shm)|db\.journal)$",
        re.IGNORECASE,
    ),
}
_TEXT_SCAN_SUFFIXES = {
    ".bat",
    ".cfg",
    ".conf",
    ".css",
    ".csv",
    ".env",
    ".err",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".key",
    ".log",
    ".txt",
    ".md",
    ".out",
    ".pem",
    ".ps1",
    ".py",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".tsv",
    ".xml",
    ".yaml",
    ".yml",
}
_MAX_SCAN_BYTES = 512_000


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _is_virtualenv_dir(name: str) -> bool:
    lowered = name.lower()
    return lowered in {".venv", "venv"} or lowered.startswith(".venv-") or lowered.startswith(".venv_") or lowered.startswith("venv-") or lowered.startswith("venv_")


def _should_ignore_path(repo_root: Path, path: Path) -> bool:
    relative_path = path.relative_to(repo_root)
    parts = relative_path.parts
    if any(part in _IGNORE_DIR_NAMES for part in parts[:-1]):
        return True
    if any(_is_virtualenv_dir(part) for part in parts[:-1]):
        return True
    if any(pattern.search(part) for part in parts[:-1] for pattern in _IGNORE_DIR_PATTERNS):
        return True
    if any(part.endswith(suffix) for suffix in _IGNORE_DIR_SUFFIXES for part in parts[:-1]):
        return True
    if path.name.lower() in _IGNORE_FILE_NAMES:
        return True
    relative_posix = relative_path.as_posix()
    return any(fnmatch.fnmatch(relative_posix, pattern) for pattern in _IGNORE_PATH_GLOBS)


def _scan_text(path: Path, text: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for label, pattern in _SECRET_PATTERNS.items():
            if pattern.search(line):
                issues.append(
                    {
                        "kind": "secret_pattern",
                        "label": label,
                        "path": str(path),
                        "line_number": line_number,
                    }
                )
    return issues


def _iter_repo_files(repo_root: Path):
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if _should_ignore_path(repo_root, path):
            continue
        yield path


def _should_scan_text(path: Path) -> bool:
    name = path.name.lower()
    if name == ".env" or name.startswith(".env."):
        return True
    return path.suffix.lower() in _TEXT_SCAN_SUFFIXES


def scan_repo_hygiene(root: Path) -> list[dict[str, Any]]:
    repo_root = Path(root)
    issues: list[dict[str, Any]] = []

    for child in repo_root.iterdir():
        if child.is_file() and child.name in _SUSPICIOUS_ROOT_FILENAMES:
            issues.append(
                {
                    "kind": "unexpected_root_file",
                    "label": child.name,
                    "path": str(child),
                }
            )
        if child.is_dir() and _is_virtualenv_dir(child.name):
            continue
        if child.is_dir() and any(pattern.search(child.name) for pattern in _IGNORE_DIR_PATTERNS):
            issues.append(
                {
                    "kind": "temporary_workspace_artifact",
                    "label": child.name,
                    "path": str(child),
                }
            )
    for path in _iter_repo_files(repo_root):
        for label, pattern in _TEMP_FILE_PATTERNS.items():
            if pattern.search(path.name):
                issues.append(
                    {
                        "kind": label,
                        "label": path.name,
                        "path": str(path),
                    }
                )
                break
        if not _should_scan_text(path):
            continue
        if path.stat().st_size > _MAX_SCAN_BYTES:
            continue
        issues.extend(_scan_text(path, _read_text(path)))

    return sorted(
        issues,
        key=lambda item: (
            item["path"],
            int(item.get("line_number", 0)),
            item["kind"],
            item["label"],
        ),
    )
