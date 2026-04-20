from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from .config import get_settings
from .entities import AuditLogEvent, User, Workspace
from .request_meta import request_ip


def _request_ip(request: Request | None) -> str:
    return request_ip(request, get_settings())


def audit_event(
    db: Session,
    *,
    request: Request | None,
    action: str,
    status: str = "ok",
    summary: str = "",
    user: User | None = None,
    workspace: Workspace | None = None,
    resource_type: str = "",
    resource_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> AuditLogEvent:
    event = AuditLogEvent(
        owner_user_id=user.id if user else None,
        workspace_id=workspace.id if workspace else None,
        route=str(request.url.path) if request else "",
        method=str(request.method) if request else "",
        action=action.strip(),
        resource_type=resource_type.strip(),
        resource_id=resource_id.strip(),
        status=status.strip() or "ok",
        ip_address=_request_ip(request),
        user_agent=str(request.headers.get("user-agent", "") if request else "")[:500],
        summary=summary.strip(),
        metadata_json=dict(metadata or {}),
    )
    db.add(event)
    db.flush()
    return event
