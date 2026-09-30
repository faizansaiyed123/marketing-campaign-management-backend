import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-with-at-least-32-bytes-long")
os.environ.setdefault("FRONTEND_ORIGIN", "http://testserver")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("PUBLIC_BASE_URL", "http://localhost:8000")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app

database_url = os.getenv("TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")
engine_kwargs = {"pool_pre_ping": True}
if database_url.startswith("sqlite"):
    engine_kwargs.update({"connect_args": {"check_same_thread": False}, "poolclass": StaticPool})
engine = create_engine(database_url, **engine_kwargs)

def override_db():
    with Session(engine) as db:
        yield db

app.dependency_overrides[get_db] = override_db

@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)

@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
