from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.services.abtest.service import reset_abtest_service_for_tests
from app.services.canary.service import reset_canary_service_for_tests


@pytest.fixture(autouse=True)
def _reset_canary_singleton() -> Generator[None, None, None]:
    reset_canary_service_for_tests()
    reset_abtest_service_for_tests()
    yield
    reset_canary_service_for_tests()
    reset_abtest_service_for_tests()


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
