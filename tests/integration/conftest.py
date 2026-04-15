from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def migrated_engine(tmp_path: Path):
    db_path = tmp_path / "constraint_scanner.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path}", future=True)

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    repo_root = Path(__file__).resolve().parents[2]
    alembic_config = Config(str(repo_root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(repo_root / "migrations"))

    with engine.begin() as connection:
        alembic_config.attributes["connection"] = connection
        command.upgrade(alembic_config, "head")

    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def session(migrated_engine) -> Iterator[Session]:
    factory = sessionmaker(bind=migrated_engine, autoflush=False, expire_on_commit=False, class_=Session)
    current_session = factory()
    try:
        yield current_session
        current_session.commit()
    finally:
        current_session.close()
