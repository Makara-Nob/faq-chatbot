r"""
Walk the whole auth flow against a running server. Re-run it any time.

    .\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
    .\venv\Scripts\python.exe scripts\demo_auth.py
"""

import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
USERNAME = "demo_user"
PASSWORD = "MyStrongPass123"


def show(step: str, response: httpx.Response) -> None:
    """Every response has the same shape, so one printer handles all of them."""
    body = response.json()
    mark = "OK  " if body.get("success") else "FAIL"
    print(f"\n{step}")
    print(f"  [{mark}] HTTP {response.status_code} | {body.get('message')}")

    data = body.get("data")
    if data is not None:
        text = str(data)
        print(f"  data: {text[:170]}{'...' if len(text) > 170 else ''}")
    if body.get("error"):
        print(f"  error: {body['error']}")


with httpx.Client(base_url=BASE, timeout=15) as c:
    show("1. POST /ask with NO credentials", c.post("/ask", json={"question": "refund policy"}))

    show(
        "2. POST /auth/register",
        c.post("/auth/register", json={"username": USERNAME, "password": PASSWORD}),
    )

    show(
        "3. POST /auth/register with a bad username (validation)",
        c.post("/auth/register", json={"username": "no spaces!", "password": "weak"}),
    )

    # plain JSON - no OAuth2 form, no client_id/client_secret
    # note the capital U: usernames are case-insensitive
    login = c.post("/auth/login", json={"username": USERNAME.upper(), "password": PASSWORD})
    show("4. POST /auth/login", login)
    tokens = login.json()["data"]

    auth = {"Authorization": f"Bearer {tokens['access_token']}"}

    show(
        "5. POST /ask WITH bearer token",
        c.post("/ask", json={"question": "how do I get a refund?", "top_k": 1}, headers=auth),
    )

    show(
        "6. POST /ask with a question nothing matches (still success)",
        c.post("/ask", json={"question": "elephant giraffe helicopter"}, headers=auth),
    )

    show("7. GET /auth/me", c.get("/auth/me", headers=auth))

    show("8. POST /admin/reload as a normal user (expect forbidden)",
         c.post("/admin/reload", headers=auth))

    key = c.post("/auth/api-keys", json={"name": "demo-key"}, headers=auth)
    show("9. POST /auth/api-keys", key)
    raw_key = key.json()["data"]["key"]

    show(
        "10. POST /ask with X-API-Key instead of a token",
        c.post("/ask", json={"question": "shipping time"}, headers={"X-API-Key": raw_key}),
    )

    show(
        "11. POST /auth/refresh (rotates the token)",
        c.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}),
    )

    show(
        "12. POST /auth/refresh REUSING the old token (expect all sessions killed)",
        c.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}),
    )

print("\ndone.")
