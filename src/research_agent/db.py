from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    return database_url


@lru_cache(maxsize=1)
def get_engine():
    settings = get_settings()
    database_url = normalize_database_url(settings.database_url)
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine_kwargs = {
        "future": True,
        "connect_args": connect_args,
    }
    if not database_url.startswith("sqlite"):
        engine_kwargs.update(
            {
                "pool_size": settings.db_pool_size,
                "max_overflow": settings.db_max_overflow,
                "pool_timeout": settings.db_pool_timeout,
                "pool_recycle": settings.db_pool_recycle,
                "pool_pre_ping": True,
            }
        )
    return create_engine(database_url, **engine_kwargs)


@lru_cache(maxsize=1)
def get_session_factory():
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_database() -> None:
    from . import entities  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(engine)
    _apply_schema_compatibility_upgrades(engine)


def _apply_schema_compatibility_upgrades(engine) -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    if "workspaces" in existing_tables:
        workspace_columns = {column["name"] for column in inspector.get_columns("workspaces")}
        workspace_statements: list[str] = []
        if "team_id" not in workspace_columns:
            workspace_statements.append("ALTER TABLE workspaces ADD COLUMN team_id VARCHAR(36) NULL")
        if "updated_at" not in workspace_columns:
            column_type = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name.startswith("postgresql") else "TIMESTAMP"
            workspace_statements.append(f"ALTER TABLE workspaces ADD COLUMN updated_at {column_type} NULL")
        if workspace_statements:
            with engine.begin() as connection:
                for statement in workspace_statements:
                    connection.execute(text(statement))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_workspaces_team_id ON workspaces (team_id)"))
                connection.execute(text("UPDATE workspaces SET updated_at = created_at WHERE updated_at IS NULL"))
    if "teams" not in existing_tables:
        from .entities import Team  # noqa: F401
        Base.metadata.tables["teams"].create(engine, checkfirst=True)
        existing_tables.add("teams")
    if "team_members" not in existing_tables:
        from .entities import TeamMember  # noqa: F401
        Base.metadata.tables["team_members"].create(engine, checkfirst=True)
        existing_tables.add("team_members")
    if "runtime_profiles" not in existing_tables:
        from .entities import RuntimeProfile  # noqa: F401
        Base.metadata.tables["runtime_profiles"].create(engine, checkfirst=True)
        existing_tables.add("runtime_profiles")
    if "runtime_bundles" not in existing_tables:
        from .entities import RuntimeBundle  # noqa: F401
        Base.metadata.tables["runtime_bundles"].create(engine, checkfirst=True)
        existing_tables.add("runtime_bundles")
    if "team_library_records" not in existing_tables:
        from .entities import TeamLibraryRecord  # noqa: F401
        Base.metadata.tables["team_library_records"].create(engine, checkfirst=True)
        existing_tables.add("team_library_records")
    if "publication_records" not in existing_tables:
        from .entities import PublicationRecord  # noqa: F401
        Base.metadata.tables["publication_records"].create(engine, checkfirst=True)
        existing_tables.add("publication_records")
    if "users" in existing_tables:
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "locked_until" not in user_columns:
            column_type = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name.startswith("postgresql") else "TIMESTAMP"
            with engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE users ADD COLUMN locked_until {column_type} NULL"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_users_locked_until ON users (locked_until)"))
    if "agent_runs" in existing_tables:
        agent_run_columns = {column["name"] for column in inspector.get_columns("agent_runs")}
        statements: list[str] = []
        if "input_json" not in agent_run_columns:
            statements.append("ALTER TABLE agent_runs ADD COLUMN input_json JSON")
        if "attachment_json" not in agent_run_columns:
            statements.append("ALTER TABLE agent_runs ADD COLUMN attachment_json JSON")
        if "candidate_drafts_json" not in agent_run_columns:
            statements.append("ALTER TABLE agent_runs ADD COLUMN candidate_drafts_json JSON")
        if "selected_draft_id" not in agent_run_columns:
            statements.append("ALTER TABLE agent_runs ADD COLUMN selected_draft_id VARCHAR(120) DEFAULT ''")
        if "workspace_knowledge_record_id" not in agent_run_columns:
            statements.append("ALTER TABLE agent_runs ADD COLUMN workspace_knowledge_record_id VARCHAR(36) NULL")
        if "workspace_case_id" not in agent_run_columns:
            statements.append("ALTER TABLE agent_runs ADD COLUMN workspace_case_id VARCHAR(36) NULL")
        if "queue_status" not in agent_run_columns:
            statements.append("ALTER TABLE agent_runs ADD COLUMN queue_status VARCHAR(40) DEFAULT 'idle'")
        if "queued_at" not in agent_run_columns:
            column_type = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name.startswith("postgresql") else "TIMESTAMP"
            statements.append(f"ALTER TABLE agent_runs ADD COLUMN queued_at {column_type} NULL")
        if "claimed_at" not in agent_run_columns:
            column_type = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name.startswith("postgresql") else "TIMESTAMP"
            statements.append(f"ALTER TABLE agent_runs ADD COLUMN claimed_at {column_type} NULL")
        if "lease_expires_at" not in agent_run_columns:
            column_type = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name.startswith("postgresql") else "TIMESTAMP"
            statements.append(f"ALTER TABLE agent_runs ADD COLUMN lease_expires_at {column_type} NULL")
        if "worker_id" not in agent_run_columns:
            statements.append("ALTER TABLE agent_runs ADD COLUMN worker_id VARCHAR(120) DEFAULT ''")
        if "worker_heartbeat_at" not in agent_run_columns:
            column_type = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name.startswith("postgresql") else "TIMESTAMP"
            statements.append(f"ALTER TABLE agent_runs ADD COLUMN worker_heartbeat_at {column_type} NULL")
        if "runtime_profile_json" not in agent_run_columns:
            statements.append("ALTER TABLE agent_runs ADD COLUMN runtime_profile_json JSON")
        if "stage_provider_json" not in agent_run_columns:
            statements.append("ALTER TABLE agent_runs ADD COLUMN stage_provider_json JSON")
        if "runtime_bundle_id" not in agent_run_columns:
            statements.append("ALTER TABLE agent_runs ADD COLUMN runtime_bundle_id VARCHAR(36) NULL")
        if "runtime_bundle_version" not in agent_run_columns:
            statements.append("ALTER TABLE agent_runs ADD COLUMN runtime_bundle_version VARCHAR(80) DEFAULT ''")
        if "quality_json" not in agent_run_columns:
            statements.append("ALTER TABLE agent_runs ADD COLUMN quality_json JSON")
        if "publish_status" not in agent_run_columns:
            statements.append("ALTER TABLE agent_runs ADD COLUMN publish_status VARCHAR(40) DEFAULT 'unpublished'")
        if "published_at" not in agent_run_columns:
            column_type = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name.startswith("postgresql") else "TIMESTAMP"
            statements.append(f"ALTER TABLE agent_runs ADD COLUMN published_at {column_type} NULL")
        if statements:
            with engine.begin() as connection:
                for statement in statements:
                    connection.execute(text(statement))
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_agent_runs_workspace_knowledge_record_id "
                        "ON agent_runs (workspace_knowledge_record_id)"
                    )
                )
                connection.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_agent_runs_workspace_case_id ON agent_runs (workspace_case_id)")
                )
                connection.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_agent_runs_queue_status ON agent_runs (queue_status)")
                )
                connection.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_agent_runs_publish_status ON agent_runs (publish_status)")
                )
                connection.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_agent_runs_runtime_bundle_id ON agent_runs (runtime_bundle_id)")
                )
                connection.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_agent_runs_runtime_bundle_version ON agent_runs (runtime_bundle_version)")
                )
                connection.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_agent_runs_worker_heartbeat_at ON agent_runs (worker_heartbeat_at)")
                )
    if "runtime_profiles" in existing_tables:
        runtime_profile_columns = {column["name"] for column in inspector.get_columns("runtime_profiles")}
        statements = []
        if "active_bundle_id" not in runtime_profile_columns:
            statements.append("ALTER TABLE runtime_profiles ADD COLUMN active_bundle_id VARCHAR(36) NULL")
        if "health_json" not in runtime_profile_columns:
            statements.append("ALTER TABLE runtime_profiles ADD COLUMN health_json JSON")
        if statements:
            with engine.begin() as connection:
                for statement in statements:
                    connection.execute(text(statement))
                connection.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_runtime_profiles_active_bundle_id ON runtime_profiles (active_bundle_id)")
                )
