from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .config import Settings
from .entities import LoginAttempt, PasswordResetToken, RateLimitBucket, User, UserSession
from .security import (
    AccountLockedError,
    RateLimitError,
    build_password_reset_expiry,
    generate_session_token,
    hash_token,
)


LOGIN_FAILURE_LIMIT = 5
LOGIN_LOCK_MINUTES = 15
LOGIN_IP_LIMIT = 20
REGISTER_IP_LIMIT = 3
DEFAULT_WINDOW_MINUTES = 60


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def purge_expired_sessions(db: Session) -> int:
    now = utc_now()
    stale = list(db.scalars(select(UserSession).where(UserSession.expires_at <= now)))
    for session in stale:
        db.delete(session)
    if stale:
        db.flush()
    return len(stale)


def purge_used_or_expired_reset_tokens(db: Session) -> int:
    now = utc_now()
    stale = list(
        db.scalars(
            select(PasswordResetToken).where(
                (PasswordResetToken.expires_at <= now) | PasswordResetToken.used_at.is_not(None)
            )
        )
    )
    for token in stale:
        db.delete(token)
    if stale:
        db.flush()
    return len(stale)


def purge_stale_login_attempts(db: Session, *, retention_days: int = 30) -> int:
    threshold = utc_now() - timedelta(days=retention_days)
    stale = list(
        db.scalars(
            select(LoginAttempt).where(
                LoginAttempt.updated_at <= threshold
            )
        )
    )
    for row in stale:
        db.delete(row)
    if stale:
        db.flush()
    return len(stale)


def _lock_until() -> datetime:
    return utc_now() + timedelta(minutes=LOGIN_LOCK_MINUTES)


def _window_reset_threshold(minutes: int) -> datetime:
    return utc_now() - timedelta(minutes=minutes)


def _login_attempt_row(db: Session, *, email: str, ip_address: str) -> LoginAttempt | None:
    return db.scalar(select(LoginAttempt).where(and_(LoginAttempt.email == email, LoginAttempt.ip_address == ip_address)))


def assert_login_allowed(db: Session, *, email: str, ip_address: str) -> None:
    now = utc_now()
    row = _login_attempt_row(db, email=email, ip_address=ip_address)
    locked_until = ensure_utc(row.locked_until) if row else None
    if row and locked_until and locked_until > now:
        raise AccountLockedError("Too many failed sign-in attempts. Try again later.")
    ip_bucket = list(
        db.scalars(
            select(LoginAttempt).where(
                and_(
                    LoginAttempt.ip_address == ip_address,
                    LoginAttempt.window_started_at >= _window_reset_threshold(DEFAULT_WINDOW_MINUTES),
                )
            )
        )
    )
    total_failures = sum(item.failed_count for item in ip_bucket)
    if total_failures >= LOGIN_IP_LIMIT:
        raise RateLimitError("Too many sign-in attempts from this IP address.")


def record_login_failure(db: Session, *, email: str, ip_address: str, user: User | None = None) -> None:
    now = utc_now()
    row = _login_attempt_row(db, email=email, ip_address=ip_address)
    if not row:
        row = LoginAttempt(email=email, ip_address=ip_address)
        db.add(row)
        db.flush()
    window_started_at = ensure_utc(row.window_started_at) or now
    if window_started_at < _window_reset_threshold(LOGIN_LOCK_MINUTES):
        row.failed_count = 0
        row.window_started_at = now
    row.failed_count += 1
    row.updated_at = now
    if row.failed_count >= LOGIN_FAILURE_LIMIT:
        row.locked_until = _lock_until()
        if user:
            user.locked_until = row.locked_until
    db.flush()


def clear_login_failures(db: Session, *, email: str, ip_address: str, user: User | None = None) -> None:
    row = _login_attempt_row(db, email=email, ip_address=ip_address)
    if row:
        db.delete(row)
    if user:
        user.locked_until = None
    if row or user:
        db.flush()


def clear_login_failures_for_email(db: Session, *, email: str, user: User | None = None) -> int:
    normalized_email = str(email or "").strip().lower()
    rows = list(db.scalars(select(LoginAttempt).where(LoginAttempt.email == normalized_email)))
    for row in rows:
        db.delete(row)
    if user:
        user.locked_until = None
    if rows or user:
        db.flush()
    return len(rows)


def consume_rate_limit(
    db: Session,
    *,
    bucket_type: str,
    bucket_key: str,
    limit: int,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
) -> None:
    now = utc_now()
    row = db.scalar(
        select(RateLimitBucket).where(
            and_(RateLimitBucket.bucket_type == bucket_type, RateLimitBucket.bucket_key == bucket_key)
        )
    )
    if not row:
        row = RateLimitBucket(bucket_type=bucket_type, bucket_key=bucket_key, count=0, window_started_at=now)
        db.add(row)
        db.flush()
    window_started_at = ensure_utc(row.window_started_at) or now
    if window_started_at < _window_reset_threshold(window_minutes):
        row.count = 0
        row.window_started_at = now
    if row.count >= limit:
        raise RateLimitError("Too many requests. Please wait and try again.")
    row.count += 1
    row.updated_at = now
    db.flush()


def issue_password_reset_token(db: Session, *, user: User, ttl_minutes: int = 30) -> str:
    purge_used_or_expired_reset_tokens(db)
    raw_token = generate_session_token()
    row = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=build_password_reset_expiry(ttl_minutes=ttl_minutes),
    )
    db.add(row)
    db.flush()
    return raw_token


def consume_password_reset_token(db: Session, *, raw_token: str) -> User:
    purge_used_or_expired_reset_tokens(db)
    row = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(raw_token)))
    expires_at = ensure_utc(row.expires_at) if row else None
    if not row or row.used_at is not None or not expires_at or expires_at <= utc_now():
        raise PermissionError("The password reset link is invalid or expired.")
    user = db.get(User, row.user_id)
    if not user or not user.is_active:
        raise PermissionError("The password reset link is invalid or expired.")
    row.used_at = utc_now()
    db.flush()
    return user


def active_session_count(db: Session, *, user: User) -> int:
    return len(
        list(
            db.scalars(
                select(UserSession).where(
                    and_(UserSession.user_id == user.id, UserSession.expires_at > utc_now())
                )
            )
        )
    )


def rate_limit_key(parts: list[Any]) -> str:
    return "::".join(str(part or "").strip() for part in parts)
