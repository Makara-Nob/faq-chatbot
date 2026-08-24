"""
Shared test setup.

JAVA: @SpringBootTest + @TestPropertySource + a @TestConfiguration.

These env vars MUST be set before `app.*` is imported, because
app/db/database.py builds the engine at import time.
"""

import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["SECRET_KEY"] = "test-secret-key-not-used-anywhere-real"
os.environ["ENV"] = "dev"
os.environ["USE_RAG"] = "false"

# Tests must not inherit the developer's .env admin - each test decides which
# users exist. Real env vars win over the .env file, so this switch is enough.
os.environ["SEED_ADMIN"] = "false"

# Uploaded files go to a throwaway directory, never the real ./storage.
os.environ["STORAGE_DIR"] = "./test_storage"

import shutil  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    """
    A fixture is pytest's dependency injection.
    autouse=True -> runs for every test without being asked for.
    Fresh schema and empty storage per test, so tests cannot leak into
    each other.
    """
    storage = Path("./test_storage")
    shutil.rmtree(storage, ignore_errors=True)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

    shutil.rmtree(storage, ignore_errors=True)


@pytest.fixture
def client():
    """`with TestClient(...)` runs the lifespan - without `with`, it does not."""
    with TestClient(app) as c:
        yield c


GOOD_PASSWORD = "Sup3rSecretPass!"


@pytest.fixture
def registered(client):
    """Registers a user and returns their credentials."""
    username = "dev_user"
    r = client.post(
        "/auth/register", json={"username": username, "password": GOOD_PASSWORD}
    )
    assert r.status_code == 201, r.text
    return {"username": username, "password": GOOD_PASSWORD, "id": r.json()["data"]["id"]}


@pytest.fixture
def tokens(client, registered):
    r = client.post(
        "/auth/login",
        json={"username": registered["username"], "password": registered["password"]},
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


@pytest.fixture
def auth_headers(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}
