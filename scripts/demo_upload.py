r"""
Demonstrate the full ingestion flow, including tenant isolation.

    .\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
    .\venv\Scripts\python.exe scripts\demo_upload.py
"""

import io
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PASSWORD = "MyStrongPass123"

COMPANY_DOC = b"""Q: What are your opening hours?
A: Monday to Friday, 9am to 6pm. Closed on public holidays.

Q: Where is the office?
A: Fourth floor, 12 Norodom Boulevard, Phnom Penh.

Q: What is the wifi password?
A: Ask the office manager; it rotates every month.
"""


def show(step: str, response: httpx.Response) -> None:
    body = response.json()
    mark = "OK  " if body.get("success") else "FAIL"
    print(f"\n{step}\n  [{mark}] HTTP {response.status_code} | {body.get('message')}")
    data = body.get("data")
    if data is not None:
        text = str(data)
        print(f"  data: {text[:200]}{'...' if len(text) > 200 else ''}")


def register_and_login(c: httpx.Client, username: str) -> dict:
    c.post("/auth/register", json={"username": username, "password": PASSWORD})
    tokens = c.post(
        "/auth/login", json={"username": username, "password": PASSWORD}
    ).json()["data"]
    return {"Authorization": f"Bearer {tokens['access_token']}"}


with httpx.Client(base_url=BASE, timeout=30) as c:
    alice = register_and_login(c, "alice_demo")
    bob = register_and_login(c, "bob_demo")

    show(
        "1. Alice asks before uploading anything (falls back to demo FAQs)",
        c.post("/ask", json={"question": "Where is the office?"}, headers=alice),
    )

    show(
        "2. Alice uploads her company handbook",
        c.post(
            "/documents",
            files={"file": ("handbook.txt", io.BytesIO(COMPANY_DOC), "text/plain")},
            headers=alice,
        ),
    )

    show(
        "3. Alice asks the same question again - now answered from HER document",
        c.post("/ask", json={"question": "Where is the office?"}, headers=alice),
    )

    show(
        "4. Bob asks the same question - he must NOT see Alice's data",
        c.post("/ask", json={"question": "Where is the office?"}, headers=bob),
    )

    show("5. Bob lists documents (his own, so empty)", c.get("/documents", headers=bob))

    show(
        "6. Upload with a path-traversal filename",
        c.post(
            "/documents",
            files={
                "file": (
                    "../../../../etc/passwd.txt",
                    io.BytesIO(b"Q: Safe?\nA: Yes, the path is stripped."),
                    "text/plain",
                )
            },
            headers=alice,
        ),
    )

    show(
        "7. Upload an unsupported type",
        c.post(
            "/documents",
            files={"file": ("virus.exe", io.BytesIO(b"MZ..."), "application/exe")},
            headers=alice,
        ),
    )

    show(
        "8. Upload something too large",
        c.post(
            "/documents",
            files={"file": ("big.txt", io.BytesIO(b"word " * 300_000), "text/plain")},
            headers=alice,
        ),
    )

    listing = c.get("/documents", headers=alice)
    show("9. Alice's document list", listing)

    doc_id = listing.json()["data"]["items"][0]["id"]
    show(
        f"10. Bob tries to delete Alice's document {doc_id}",
        c.delete(f"/documents/{doc_id}", headers=bob),
    )

print("\ndone.")
