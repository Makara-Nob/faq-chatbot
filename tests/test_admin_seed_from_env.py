"""
Tests for the startup seed that reads ADMIN_USERNAME / ADMIN_PASSWORD.

These call the seeding function directly with a patched Settings object, which
is much faster and clearer than restarting the app with different env vars.

JAVA: the same idea as @MockBean on a @ConfigurationProperties class.
"""

from unittest.mock import patch

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import User
from app.main import seed_admin_from_settings


class FakeSettings:
    """Stands in for the real Settings object."""

    def __init__(self, **kwargs):
        self.seed_admin = kwargs.get("seed_admin", True)
        self.admin_username = kwargs.get("admin_username", "env_admin")
        self.admin_password = kwargs.get("admin_password", "EnvAdminPass123")
        self.is_prod = kwargs.get("is_prod", False)


def seed_with(**kwargs) -> None:
    with patch("app.main.settings", FakeSettings(**kwargs)):
        seed_admin_from_settings()


def all_users() -> list[User]:
    with SessionLocal() as db:
        return list(db.execute(select(User)).scalars().all())


def test_seeds_the_admin_from_config(client):
    seed_with()

    users = all_users()
    assert len(users) == 1
    assert users[0].username == "env_admin"
    assert users[0].role == "admin"


def test_seeded_admin_can_log_in(client):
    seed_with()

    r = client.post(
        "/auth/login",
        json={"username": "env_admin", "password": "EnvAdminPass123"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["access_token"]


def test_second_boot_does_not_change_the_password(client):
    """Editing ADMIN_PASSWORD must not silently rewrite a live credential."""
    seed_with()
    original = all_users()[0].hashed_password

    seed_with(admin_password="TotallyDifferent9")

    assert len(all_users()) == 1
    assert all_users()[0].hashed_password == original
    # the original password still works
    r = client.post(
        "/auth/login",
        json={"username": "env_admin", "password": "EnvAdminPass123"},
    )
    assert r.status_code == 200


def test_skipped_when_seed_admin_is_false(client):
    seed_with(seed_admin=False)
    assert all_users() == []


def test_skipped_when_config_is_missing(client):
    seed_with(admin_username=None, admin_password=None)
    assert all_users() == []


def test_weak_seed_password_is_refused_without_crashing(client):
    """A bad value in .env must not take the whole app down at boot."""
    seed_with(admin_password="weak")
    assert all_users() == []


def test_invalid_seed_username_is_refused_without_crashing(client):
    seed_with(admin_username="has spaces")
    assert all_users() == []
