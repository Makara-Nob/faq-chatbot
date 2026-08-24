"""
Tests for the security properties - not just "does it return 200".

Each test is named after the rule it defends. If someone later breaks the
rule, the test name tells them what they broke.
"""

from app.core.ratelimit import login_limiter
from tests.conftest import GOOD_PASSWORD


def login(client, username, password):
    return client.post(
        "/auth/login", json={"username": username, "password": password}
    )


# --- the response envelope -------------------------------------------------

def test_success_response_has_envelope(client):
    r = client.get("/health")
    body = r.json()
    assert body["success"] is True
    assert body["message"] == "Service is healthy"
    assert body["data"]["status"] == "ok"


def test_failure_response_has_same_envelope(client):
    r = login(client, "nobody", "Wrong1Password!")
    body = r.json()
    assert r.status_code == 401
    assert body["success"] is False
    assert body["message"] == "Incorrect username or password"
    assert body["data"] is None
    assert body["error"]["code"] == "unauthorized"
    assert body["request_id"]


def test_validation_error_reports_the_field(client):
    r = client.post("/auth/register", json={"username": "a b!", "password": "x"})
    body = r.json()
    assert r.status_code == 422
    assert body["success"] is False
    assert body["error"]["code"] == "validation_error"
    assert "username" in body["error"]["fields"]
    assert "password" in body["error"]["fields"]


# --- registration ----------------------------------------------------------

def test_register_returns_user_without_password_hash(client):
    r = client.post(
        "/auth/register", json={"username": "alice", "password": GOOD_PASSWORD}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["success"] is True
    assert body["message"] == "Account created successfully"

    data = body["data"]
    assert data["username"] == "alice"
    assert data["role"] == "user"
    # the whole point of a separate response model:
    assert "hashed_password" not in data
    assert "password" not in data


def test_weak_password_is_rejected(client):
    for bad in ["short", "alllowercase123", "NoDigitsHereAtAll"]:
        r = client.post("/auth/register", json={"username": "bob", "password": bad})
        assert r.status_code == 422, f"{bad!r} should have been rejected"
        assert r.json()["success"] is False


def test_duplicate_username_conflicts(client, registered):
    r = client.post(
        "/auth/register",
        json={"username": registered["username"], "password": GOOD_PASSWORD},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


def test_usernames_are_case_insensitive(client):
    """
    "Admin" and "admin" must be the SAME account. Otherwise a user who
    capitalises at login can never get in, and an attacker can register a
    lookalike of an existing name.
    """
    client.post("/auth/register", json={"username": "Carol", "password": GOOD_PASSWORD})

    # stored lowercase
    r = client.post("/auth/register", json={"username": "carol", "password": GOOD_PASSWORD})
    assert r.status_code == 409

    # and any capitalisation logs in
    for variant in ["carol", "Carol", "CAROL", "cArOl"]:
        assert login(client, variant, GOOD_PASSWORD).status_code == 200


def test_surrounding_whitespace_is_trimmed(client):
    client.post("/auth/register", json={"username": "dave", "password": GOOD_PASSWORD})
    assert login(client, "  dave  ", GOOD_PASSWORD).status_code == 200


def test_invalid_username_characters_are_rejected(client):
    """No spaces, no @, no unicode lookalikes ("аdmin" with a Cyrillic а)."""
    for bad in ["has space", "user@host", "admin!", "аdmin", "ab", "x" * 51, ""]:
        r = client.post("/auth/register", json={"username": bad, "password": GOOD_PASSWORD})
        assert r.status_code == 422, f"{bad!r} should have been rejected"


def test_valid_username_characters_are_accepted(client):
    for good in ["makara", "user_1", "first.last", "a-b-c", "ABC123"]:
        r = client.post("/auth/register", json={"username": good, "password": GOOD_PASSWORD})
        assert r.status_code == 201, f"{good!r} should have been accepted: {r.text}"


# --- login -----------------------------------------------------------------

def test_login_returns_token_pair(client, registered):
    r = login(client, registered["username"], registered["password"])
    assert r.status_code == 200
    body = r.json()
    assert body["message"] == "Login successful"

    data = body["data"]
    assert data["token_type"] == "bearer"
    assert data["access_token"] and data["refresh_token"]
    assert data["expires_in"] == 15 * 60


def test_wrong_password_and_unknown_user_give_identical_errors(client, registered):
    """If these differ, the login form becomes an account-existence oracle."""
    wrong_pw = login(client, registered["username"], "Wrong1Password!")
    no_user = login(client, "nobody", "Wrong1Password!")

    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json()["message"] == no_user.json()["message"]


def test_login_is_rate_limited(client, registered):
    login_limiter.reset("login:testclient")
    for _ in range(5):
        login(client, registered["username"], "Bad1Password!")

    r = login(client, registered["username"], "Bad1Password!")
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
    # the protocol header must survive the envelope rewrite
    assert "Retry-After" in r.headers
    login_limiter.reset("login:testclient")


# --- protected routes ------------------------------------------------------

def test_ask_requires_authentication(client):
    r = client.post("/ask", json={"question": "how do I get a refund?"})
    assert r.status_code == 401
    assert r.json()["success"] is False
    assert r.headers["WWW-Authenticate"] == "Bearer"


def test_ask_works_with_bearer_token(client, auth_headers):
    r = client.post(
        "/ask", json={"question": "how do I get a refund?"}, headers=auth_headers
    )
    assert r.status_code == 200
    body = r.json()
    assert body["message"] == "Answer found"
    assert "refund" in body["data"]["answer"].lower()


def test_no_match_is_still_a_success(client, auth_headers):
    """An empty result is not a failed request."""
    # words that appear nowhere in data/faqs.txt.
    # ("xxxx" would match - the support FAQ contains 1-800-XXX-XXXX.)
    r = client.post(
        "/ask", json={"question": "elephant giraffe helicopter"}, headers=auth_headers
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["message"] == "No matching FAQ found"
    assert body["data"]["sources"] == []


def test_garbage_token_is_rejected(client):
    r = client.post(
        "/ask",
        json={"question": "anything at all"},
        headers={"Authorization": "Bearer not.a.real.token"},
    )
    assert r.status_code == 401


def test_health_is_public(client):
    assert client.get("/health").status_code == 200


# --- roles -----------------------------------------------------------------

def test_normal_user_cannot_reach_admin_route(client, auth_headers):
    r = client.post("/admin/reload", headers=auth_headers)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


def test_admin_can_reach_admin_route(client, registered, auth_headers):
    from sqlalchemy import select

    from app.db.database import SessionLocal
    from app.db.models import User

    with SessionLocal() as db:
        user = db.execute(
            select(User).where(User.username == registered["username"])
        ).scalar_one()
        user.role = "admin"
        db.commit()

    # old token still says role=user, but authorization reads the DB row,
    # so the promotion takes effect immediately
    r = client.post("/admin/reload", headers=auth_headers)
    assert r.status_code == 202
    assert r.json()["success"] is True


def test_disabled_account_is_locked_out(client, registered, auth_headers):
    from sqlalchemy import select

    from app.db.database import SessionLocal
    from app.db.models import User

    with SessionLocal() as db:
        user = db.execute(
            select(User).where(User.username == registered["username"])
        ).scalar_one()
        user.is_active = False
        db.commit()

    r = client.post("/ask", json={"question": "refund policy"}, headers=auth_headers)
    assert r.status_code == 403


# --- refresh token rotation ------------------------------------------------

def test_refresh_returns_new_pair(client, tokens):
    r = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    assert r.json()["data"]["refresh_token"] != tokens["refresh_token"]


def test_reusing_a_rotated_refresh_token_kills_all_sessions(client, tokens):
    first = tokens["refresh_token"]

    second = client.post("/auth/refresh", json={"refresh_token": first}).json()["data"]
    assert client.post("/auth/refresh", json={"refresh_token": first}).status_code == 401

    # the replacement is dead too - a leak invalidates the whole chain
    r = client.post("/auth/refresh", json={"refresh_token": second["refresh_token"]})
    assert r.status_code == 401


def test_logout_revokes_the_refresh_token(client, tokens, auth_headers):
    r = client.post(
        "/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["message"] == "Logged out"

    r = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401


# --- API keys --------------------------------------------------------------

def test_api_key_authenticates_and_can_be_revoked(client, auth_headers):
    created = client.post(
        "/auth/api-keys", json={"name": "ci-pipeline"}, headers=auth_headers
    )
    assert created.status_code == 201
    raw_key = created.json()["data"]["key"]
    assert raw_key.startswith("faq_")

    r = client.post(
        "/ask", json={"question": "refund policy"}, headers={"X-API-Key": raw_key}
    )
    assert r.status_code == 200

    key_id = created.json()["data"]["id"]
    revoked = client.delete(f"/auth/api-keys/{key_id}", headers=auth_headers)
    assert revoked.status_code == 200
    assert revoked.json()["message"] == "API key revoked"

    r = client.post(
        "/ask", json={"question": "refund policy"}, headers={"X-API-Key": raw_key}
    )
    assert r.status_code == 401


def test_user_cannot_revoke_another_users_api_key(client, auth_headers):
    """IDOR: the most common real-world API vulnerability."""
    created = client.post(
        "/auth/api-keys", json={"name": "victim-key"}, headers=auth_headers
    )
    key_id = created.json()["data"]["id"]

    client.post(
        "/auth/register", json={"username": "attacker", "password": GOOD_PASSWORD}
    )
    attacker = login(client, "attacker", GOOD_PASSWORD).json()["data"]

    r = client.delete(
        f"/auth/api-keys/{key_id}",
        headers={"Authorization": f"Bearer {attacker['access_token']}"},
    )
    assert r.status_code == 404


# --- errors ----------------------------------------------------------------

def test_error_response_carries_a_request_id(client, auth_headers):
    r = client.get("/faqs/9999", headers=auth_headers)
    assert r.status_code == 404
    assert "X-Request-ID" in r.headers
    assert r.json()["request_id"] == r.headers["X-Request-ID"]
