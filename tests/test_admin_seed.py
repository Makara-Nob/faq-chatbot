"""
Tests for admin bootstrapping.

The rules being defended:
  - the seeded admin can actually reach admin routes
  - running the seed twice does not fail and does not reset the password
  - nobody can make themselves an admin through the public API
"""

import pytest

from app.db.database import SessionLocal
from app.services.user_service import (
    UsernameAlreadyExists,
    create_user,
    ensure_admin,
    set_password,
)
from tests.conftest import GOOD_PASSWORD

ADMIN_USERNAME = "boss"
ADMIN_PASSWORD = "SeededAdminPass1"


def login(client, username, password):
    return client.post(
        "/auth/login", json={"username": username, "password": password}
    )


def test_ensure_admin_creates_an_admin(client):
    with SessionLocal() as db:
        user, created = ensure_admin(db, ADMIN_USERNAME, ADMIN_PASSWORD)

    assert created is True
    assert user.role == "admin"
    assert user.is_active is True
    assert user.hashed_password != ADMIN_PASSWORD      # stored hashed, obviously


def test_seeded_admin_can_reach_admin_routes(client):
    with SessionLocal() as db:
        ensure_admin(db, ADMIN_USERNAME, ADMIN_PASSWORD)

    tokens = login(client, ADMIN_USERNAME, ADMIN_PASSWORD).json()["data"]
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    assert client.get("/auth/me", headers=headers).json()["data"]["role"] == "admin"

    r = client.post("/admin/reload", headers=headers)
    assert r.status_code == 202
    assert r.json()["success"] is True


def test_running_the_seed_twice_is_safe(client):
    with SessionLocal() as db:
        first, created_first = ensure_admin(db, ADMIN_USERNAME, ADMIN_PASSWORD)
        original_hash = first.hashed_password

        second, created_second = ensure_admin(db, ADMIN_USERNAME, "CompletelyDifferent9")

    assert created_first is True
    assert created_second is False
    assert second.id == first.id
    # the password must NOT be silently reset by a re-run
    assert second.hashed_password == original_hash

    # and the original password still works
    assert login(client, ADMIN_USERNAME, ADMIN_PASSWORD).status_code == 200


def test_ensure_admin_promotes_an_existing_normal_user(client):
    with SessionLocal() as db:
        created = create_user(db, ADMIN_USERNAME, ADMIN_PASSWORD, role="user")
        assert created.role == "user"

        promoted, was_created = ensure_admin(db, ADMIN_USERNAME, "irrelevant-Pass1")

    assert was_created is False
    assert promoted.role == "admin"


def test_ensure_admin_reactivates_a_disabled_account(client):
    with SessionLocal() as db:
        user = create_user(db, ADMIN_USERNAME, ADMIN_PASSWORD)
        user.is_active = False
        db.commit()

        restored, _ = ensure_admin(db, ADMIN_USERNAME, ADMIN_PASSWORD)

    assert restored.is_active is True
    assert restored.role == "admin"


def test_password_reset_invalidates_the_old_password(client):
    with SessionLocal() as db:
        user, _ = ensure_admin(db, ADMIN_USERNAME, ADMIN_PASSWORD)
        set_password(db, user, "BrandNewPassword9")

    assert login(client, ADMIN_USERNAME, ADMIN_PASSWORD).status_code == 401
    assert login(client, ADMIN_USERNAME, "BrandNewPassword9").status_code == 200


def test_password_reset_kills_existing_sessions(client):
    """
    Otherwise resetting the password of a stolen account achieves nothing -
    the attacker just keeps refreshing.
    """
    with SessionLocal() as db:
        ensure_admin(db, ADMIN_USERNAME, ADMIN_PASSWORD)

    stolen = login(client, ADMIN_USERNAME, ADMIN_PASSWORD).json()["data"]

    with SessionLocal() as db:
        user, _ = ensure_admin(db, ADMIN_USERNAME, ADMIN_PASSWORD)
        revoked = set_password(db, user, "BrandNewPassword9")

    assert revoked == 1
    r = client.post("/auth/refresh", json={"refresh_token": stolen["refresh_token"]})
    assert r.status_code == 401


def test_create_user_rejects_a_duplicate_username(client):
    with SessionLocal() as db:
        create_user(db, ADMIN_USERNAME, ADMIN_PASSWORD)
        with pytest.raises(UsernameAlreadyExists):
            create_user(db, ADMIN_USERNAME, ADMIN_PASSWORD)


def test_create_user_rejects_an_unknown_role(client):
    with SessionLocal() as db, pytest.raises(ValueError):
        create_user(db, ADMIN_USERNAME, ADMIN_PASSWORD, role="superuser")


def test_public_registration_cannot_grant_itself_a_role(client):
    """Mass assignment: passing extra fields must not make you an admin."""
    r = client.post(
        "/auth/register",
        json={
            "username": "sneaky",
            "password": GOOD_PASSWORD,
            "role": "admin",          # ignored - not a field on UserCreate
            "is_active": True,
        },
    )
    assert r.status_code == 201
    assert r.json()["data"]["role"] == "user"


def test_generated_password_passes_our_own_rules():
    """The generator must satisfy the registration validator every time."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from create_admin import generate_password

    from app.schemas.auth import UserCreate

    for _ in range(50):
        pw = generate_password()
        UserCreate(username="tester", password=pw)   # raises if invalid
