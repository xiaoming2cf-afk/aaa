from __future__ import annotations

import math
import re
from typing import Any


_TOKEN_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")
_SOURCE_PRIOR = {
    "workspace_knowledge": 1.15,
    "team_library": 1.05,
    "method_hint": 0.95,
    "processing_catalog": 0.9,
    "model_catalog": 0.9,
}


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in _TOKEN_RE.findall(text or "")
        if len(token) > 2
    }


def _candidate_text(candidate: dict[str, Any]) -> str:
    parts = [
        str(candidate.get("title") or ""),
        str(candidate.get("summary") or ""),
        " ".join(str(tag) for tag in (candidate.get("tags") or [])),
        str((candidate.get("interface") or {}).get("method") or ""),
        str((candidate.get("interface") or {}).get("slug") or ""),
    ]
    return " ".join(part for part in parts if part).strip()


def rank_retrieval_candidates(
    *,
    query_text: str,
    candidates: list[dict[str, Any]],
    limit: int = 10,
    mode: str = "off",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    query_tokens = _tokens(query_text)
    scored: list[dict[str, Any]] = []
    for candidate in candidates:
        text = _candidate_text(candidate).lower()
        hits = sum(1 for token in query_tokens if token in text)
        prior = float(_SOURCE_PRIOR.get(str(candidate.get("source_type") or ""), 1.0))
        admissibility = 1.0 if str(candidate.get("policy") or "").strip() == "interface_only_no_external_source_injection" else 0.7
        raw = float(hits + 1) * prior * admissibility
        scored.append(
            {
                "candidate": candidate,
                "hits": hits,
                "prior": prior,
                "admissibility": admissibility,
                "raw": raw,
            }
        )

    denominator = sum(item["raw"] for item in scored)
    if denominator <= 0:
        denominator = float(len(scored) or 1)
    ranked = []
    for item in scored:
        posterior = item["raw"] / denominator
        updated = dict(item["candidate"])
        updated["score"] = max(int(updated.get("score") or 0), max(1, int(round(posterior * 1000))))
        updated["arbiter"] = {
            "surrogate_probability": round(posterior, 6),
            "lexical_hits": item["hits"],
            "prior": round(item["prior"], 4),
            "admissibility": round(item["admissibility"], 4),
            "mode": mode,
        }
        ranked.append(updated)

    ranked.sort(
        key=lambda item: (
            float((item.get("arbiter") or {}).get("surrogate_probability") or 0.0),
            int(item.get("score") or 0),
            str(item.get("title") or ""),
        ),
        reverse=True,
    )
    selected = ranked[: max(1, limit)]
    trace = {
        "mode": mode,
        "query_tokens": sorted(query_tokens),
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "surrogate": "candidate_set_normalized_lexical_prior",
        "items": [
            {
                "id": str(item.get("id") or ""),
                "title": str(item.get("title") or ""),
                "source_type": str(item.get("source_type") or ""),
                "surrogate_probability": float((item.get("arbiter") or {}).get("surrogate_probability") or 0.0),
                "lexical_hits": int((item.get("arbiter") or {}).get("lexical_hits") or 0),
            }
            for item in selected
        ],
    }
    return selected, trace
