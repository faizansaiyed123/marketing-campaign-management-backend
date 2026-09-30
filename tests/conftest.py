import os
os.environ["DATABASE_URL"]="sqlite+pysqlite:///:memory:"
os.environ["JWT_SECRET_KEY"]="test-secret"
os.environ["FRONTEND_ORIGIN"]="http://testserver"
os.environ["COOKIE_SECURE"]="false"
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.db import Base,get_db
from app.main import app
engine=create_engine("sqlite+pysqlite:///:memory:",connect_args={"check_same_thread":False},poolclass=StaticPool)
Base.metadata.create_all(engine)
def override_db():
    with Session(engine) as db: yield db
app.dependency_overrides[get_db]=override_db
@pytest.fixture()
def client():
    with TestClient(app) as c: yield c
