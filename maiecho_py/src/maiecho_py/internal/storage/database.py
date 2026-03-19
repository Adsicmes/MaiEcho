from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from maiecho_py.internal.model import Base


def _resolve_sqlite_url(database_url: str) -> str:
    if database_url == ":memory:":
        return "sqlite:///:memory:"

    if "://" in database_url:
        return database_url

    path = Path(database_url)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.resolve().as_posix()}"


@dataclass(slots=True)
class Database:
    engine: Engine
    session_factory: sessionmaker[Session]

    def session(self) -> Session:
        return self.session_factory()

    def dispose(self) -> None:
        self.engine.dispose()


def _synchronize_sqlite_columns(engine: Engine) -> None:
    column_specs: dict[str, dict[str, str]] = {
        "songs": {
            "bpm": "FLOAT",
            "release_date": "VARCHAR(100)",
            "cover_url": "VARCHAR(1024)",
        },
        "charts": {
            "notes": "TEXT",
            "charter": "VARCHAR(255)",
            "avg_achievement": "FLOAT",
            "avg_dx": "FLOAT",
            "std_dev": "FLOAT",
            "sample_count": "INTEGER",
        },
        "comments": {
            "chart_id": "INTEGER",
            "external_id": "VARCHAR(128)",
            "post_date": "DATETIME",
            "search_tag": "VARCHAR(255)",
            "sentiment": "FLOAT",
        },
        "analysis_results": {
            "rating_advice": "TEXT",
            "difficulty_analysis": "TEXT",
            "reasoning_log": "TEXT",
            "payload_json": "TEXT",
        },
        "videos": {
            "description": "TEXT",
            "author": "VARCHAR(255)",
            "publish_time": "DATETIME",
        },
    }

    with engine.begin() as connection:
        for table_name, specs in column_specs.items():
            pragma_rows = connection.execute(
                text(f"PRAGMA table_info({table_name})")
            ).mappings()
            existing = {str(row["name"]) for row in pragma_rows}
            for column_name, ddl in specs.items():
                if column_name in existing:
                    continue
                connection.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")
                )


def build_database(database_url: str) -> Database:
    resolved_url = _resolve_sqlite_url(database_url)
    engine_kwargs: dict[str, object] = {"future": True}
    if resolved_url.startswith("sqlite:///"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    if resolved_url == "sqlite:///:memory:":
        engine_kwargs["poolclass"] = StaticPool

    engine = create_engine(resolved_url, **engine_kwargs)
    Base.metadata.create_all(engine)
    if engine.dialect.name == "sqlite":
        _synchronize_sqlite_columns(engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    return Database(engine=engine, session_factory=session_factory)
