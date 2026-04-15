from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from constraint_scanner.config.loader import get_settings


def get_engine(url: str | None = None, *, echo: bool | None = None) -> Engine:
    settings = get_settings()
    database_url = url or settings.database.sqlalchemy_url()
    engine = create_engine(
        database_url,
        echo=settings.database.echo if echo is None else echo,
        pool_pre_ping=True,
        future=True,
    )

    if make_url(database_url).get_backend_name() == "sqlite":
        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def make_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    bind = engine or get_engine()
    return sessionmaker(bind=bind, autoflush=False, expire_on_commit=False, class_=Session)


@contextmanager
def get_session(engine: Engine | None = None) -> Iterator[Session]:
    session_factory = make_session_factory(engine)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
