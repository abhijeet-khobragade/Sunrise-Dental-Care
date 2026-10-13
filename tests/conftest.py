from datetime import datetime

import pytest
from sqlalchemy.pool import StaticPool

from app.config import KNOWLEDGE_DIR
from app.database import make_session_factory
from app.knowledge import KnowledgeBase

# A fixed "now" (a Monday morning) so tests give the same result every day.
NOW = datetime(2026, 10, 12, 10, 15)


@pytest.fixture
def session_factory():
    # Fresh in-memory database for every test
    return make_session_factory("sqlite://", poolclass=StaticPool)


@pytest.fixture
def db(session_factory):
    with session_factory() as session:
        yield session


@pytest.fixture(scope="session")
def kb():
    return KnowledgeBase.from_folder(KNOWLEDGE_DIR)
