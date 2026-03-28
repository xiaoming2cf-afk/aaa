from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .models import WorkRecord


def slugify(value: str, max_length: int = 64) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "-", value).strip("-").lower()
    if not cleaned:
        return "research-topic"
    return cleaned[:max_length].strip("-") or "research-topic"


def utc_timestamp_slug() -> str:
    return datetime.utcnow().strftime("%Y%m%d-%H%M%S")


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    if not inverted_index:
        return ""
    positions: dict[int, str] = {}
    for token, indexes in inverted_index.items():
        for index in indexes:
            positions[index] = token
    ordered = [positions[index] for index in sorted(positions)]
    text = " ".join(ordered)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


def truncate_text(text: str, limit: int = 8000) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def citation_key(record: WorkRecord) -> str:
    first_author = record.authors[0].split()[-1] if record.authors else "unknown"
    year = str(record.publication_year or "nd")
    title_token = re.sub(r"[^A-Za-z0-9]+", "", record.title.split()[0] if record.title else "work")
    return f"{first_author.lower()}{year}{title_token.lower()}"


def work_to_bibtex(record: WorkRecord) -> str:
    entry_type = "article" if record.venue else "misc"
    key = citation_key(record)
    author_value = " and ".join(record.authors) if record.authors else "Unknown"
    fields = {
        "title": record.title,
        "author": author_value,
        "year": str(record.publication_year or ""),
        "journal": record.venue or "",
        "doi": (record.doi or "").replace("https://doi.org/", ""),
        "url": record.landing_page_url or record.pdf_url or "",
    }
    rendered_fields = []
    for name, value in fields.items():
        if value:
            rendered_fields.append(f"  {name} = {{{value}}}")
    body = ",\n".join(rendered_fields)
    return f"@{entry_type}{{{key},\n{body}\n}}"


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_source_ids(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for match in re.findall(r"\[([A-Z]\d+)\]", text):
        seen[match] = None
    return list(seen.keys())


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def unique_preserve_order(values: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        if value:
            seen[value] = None
    return list(seen.keys())
