from __future__ import annotations

import re

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .entities import EconomicBriefing, KnowledgeRecord, LiteratureEntry, User, Workspace, WorkspaceMemory
from .runtime_models import ContextSnippet, WorkspaceContextPack
from .utils import truncate_text


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "with",
    "研究",
    "分析",
}


def _keywords(*values: str | None) -> set[str]:
    text = " ".join(value or "" for value in values).lower()
    tokens = {
        token
        for token in re.findall(r"[a-z0-9\u4e00-\u9fff]{2,}", text)
        if token not in _STOPWORDS
    }
    return tokens


def _score(topic_tokens: set[str], title: str, body: str) -> int:
    haystack_tokens = _keywords(title, body)
    overlap = topic_tokens & haystack_tokens
    if not overlap:
        return 0
    return len(overlap)


def build_workspace_context_pack(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    topic: str,
    research_question: str | None = None,
    max_memories: int = 4,
    max_notes: int = 4,
    max_briefings: int = 2,
    max_literature: int = 3,
) -> WorkspaceContextPack:
    topic_tokens = _keywords(topic, research_question or "")
    snippets: list[ContextSnippet] = []

    memory_rows = list(
        db.scalars(
            select(WorkspaceMemory)
            .where(
                and_(
                    WorkspaceMemory.owner_user_id == user.id,
                    WorkspaceMemory.workspace_id == workspace.id,
                )
            )
            .order_by(WorkspaceMemory.updated_at.desc(), WorkspaceMemory.created_at.desc())
            .limit(max(1, max_memories * 3))
        )
    )
    for row in memory_rows:
        score = _score(topic_tokens, row.title or "", row.content or "")
        if score <= 0:
            continue
        snippets.append(
            ContextSnippet(
                source_type="memory",
                record_id=row.id,
                title=row.title or "Workspace memory",
                excerpt=truncate_text(row.content or "", 220),
                relevance_score=score,
            )
        )

    note_rows = list(
        db.scalars(
            select(KnowledgeRecord)
            .where(
                and_(
                    KnowledgeRecord.owner_user_id == user.id,
                    KnowledgeRecord.workspace_id == workspace.id,
                )
            )
            .order_by(KnowledgeRecord.updated_at.desc(), KnowledgeRecord.created_at.desc())
            .limit(max(1, max_notes * 3))
        )
    )
    for row in note_rows:
        metadata = row.metadata_json or {}
        if str(metadata.get("source_type") or "").strip() == "workspace_digest":
            continue
        score = _score(topic_tokens, row.title or "", row.content or "")
        if score <= 0:
            continue
        snippets.append(
            ContextSnippet(
                source_type="note",
                record_id=row.id,
                title=row.title,
                excerpt=truncate_text(row.content or "", 240),
                relevance_score=score,
            )
        )

    briefings = list(
        db.scalars(
            select(EconomicBriefing)
            .where(
                and_(
                    EconomicBriefing.owner_user_id == user.id,
                    EconomicBriefing.workspace_id == workspace.id,
                )
            )
            .order_by(EconomicBriefing.created_at.desc())
            .limit(max(1, max_briefings * 3))
        )
    )
    for briefing in briefings:
        body = briefing.summary_markdown or ""
        score = _score(topic_tokens, briefing.title, body)
        if score <= 0:
            continue
        snippets.append(
            ContextSnippet(
                source_type="briefing",
                record_id=briefing.id,
                title=briefing.title,
                excerpt=truncate_text(body, 220),
                relevance_score=score,
            )
        )

    literature = list(
        db.scalars(
            select(LiteratureEntry)
            .where(
                and_(
                    LiteratureEntry.owner_user_id == user.id,
                    LiteratureEntry.workspace_id == workspace.id,
                )
            )
            .order_by(LiteratureEntry.updated_at.desc(), LiteratureEntry.created_at.desc())
            .limit(max(1, max_literature * 3))
        )
    )
    for entry in literature:
        body = " ".join(
            value
            for value in [
                entry.abstract or "",
                " ".join(entry.keywords_json or []),
            ]
            if value
        )
        score = _score(topic_tokens, entry.title or "", body)
        if score <= 0:
            continue
        snippets.append(
            ContextSnippet(
                source_type="literature",
                record_id=entry.id,
                title=entry.title,
                excerpt=truncate_text(body, 220),
                relevance_score=score,
            )
        )

    snippets.sort(key=lambda item: (-item.relevance_score, item.source_type, item.title.lower()))

    type_limits = {
        "memory": max_memories,
        "note": max_notes,
        "briefing": max_briefings,
        "literature": max_literature,
    }
    selected: list[ContextSnippet] = []
    counts = {key: 0 for key in type_limits}
    for snippet in snippets:
        if counts[snippet.source_type] >= type_limits[snippet.source_type]:
            continue
        selected.append(snippet)
        counts[snippet.source_type] += 1

    summary = (
        f"Workspace context for {workspace.name}: "
        f"{counts['memory']} memories, {counts['note']} notes, "
        f"{counts['briefing']} briefings, {counts['literature']} literature snippets selected."
    )

    return WorkspaceContextPack(
        workspace_id=workspace.id,
        topic=topic,
        research_question=research_question,
        summary=summary,
        snippets=selected,
    )

