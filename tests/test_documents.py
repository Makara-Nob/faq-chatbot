"""
Document upload and ingestion.

The rules being defended:
  - one user can never see or search another user's documents
  - a hostile filename cannot escape the storage directory
  - a huge or binary upload is rejected, not ingested
"""

import io

from app.services.ingestion import chunk_text, safe_display_name
from tests.conftest import GOOD_PASSWORD

SAMPLE = b"""Q: What are your opening hours?
A: We are open Monday to Friday, 9am to 6pm.

Q: Where is the office?
A: Fourth floor, 12 Norodom Boulevard, Phnom Penh.

Q: How do I contact the team?
A: Email team@example.com or call the front desk.
"""


def upload(client, headers, content=SAMPLE, filename="handbook.txt"):
    return client.post(
        "/documents",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
        headers=headers,
    )


def second_user(client):
    """Register another account and return its auth headers."""
    client.post(
        "/auth/register", json={"username": "otheruser", "password": GOOD_PASSWORD}
    )
    tokens = client.post(
        "/auth/login", json={"username": "otheruser", "password": GOOD_PASSWORD}
    ).json()["data"]
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# --- upload ----------------------------------------------------------------

def test_upload_ingests_and_chunks(client, auth_headers):
    r = upload(client, auth_headers)
    assert r.status_code == 201, r.text

    body = r.json()
    assert body["success"] is True
    assert body["data"]["filename"] == "handbook.txt"
    assert body["data"]["chunk_count"] == 3          # three Q&A pairs
    assert "3 chunk(s)" in body["message"]


def test_upload_requires_authentication(client):
    r = client.post(
        "/documents", files={"file": ("a.txt", io.BytesIO(SAMPLE), "text/plain")}
    )
    assert r.status_code == 401


def test_uploading_the_same_bytes_twice_does_not_duplicate(client, auth_headers):
    first = upload(client, auth_headers).json()["data"]
    second = upload(client, auth_headers).json()["data"]

    assert first["id"] == second["id"]

    listing = client.get("/documents", headers=auth_headers).json()["data"]
    assert listing["total"] == 1


def test_rejects_unsupported_extension(client, auth_headers):
    r = upload(client, auth_headers, filename="payload.exe")
    assert r.status_code == 415
    assert r.json()["success"] is False


def test_rejects_binary_content(client, auth_headers):
    r = upload(client, auth_headers, content=b"\x89PNG\r\n\x1a\n\x00\x00binary")
    assert r.status_code == 415


def test_rejects_empty_file(client, auth_headers):
    r = upload(client, auth_headers, content=b"   \n  \n")
    assert r.status_code == 422


def test_rejects_oversized_file(client, auth_headers):
    too_big = b"word " * 300_000                      # ~1.5 MB, limit is 1 MB
    r = upload(client, auth_headers, content=too_big)
    assert r.status_code == 413
    assert "too large" in r.json()["message"].lower()


def test_hostile_filename_is_neutralised(client, auth_headers):
    r = upload(client, auth_headers, filename="../../../../etc/passwd.txt")
    assert r.status_code == 201
    # directory components stripped, nothing left to traverse with
    assert r.json()["data"]["filename"] == "passwd.txt"


def test_stored_path_is_never_exposed(client, auth_headers):
    data = upload(client, auth_headers).json()["data"]
    assert "stored_path" not in data
    assert "content_hash" not in data


# --- tenancy ---------------------------------------------------------------

def test_users_cannot_see_each_others_documents(client, auth_headers):
    upload(client, auth_headers)
    other = second_user(client)

    listing = client.get("/documents", headers=other).json()["data"]
    assert listing["total"] == 0


def test_users_cannot_fetch_each_others_documents_by_id(client, auth_headers):
    doc_id = upload(client, auth_headers).json()["data"]["id"]
    other = second_user(client)

    assert client.get(f"/documents/{doc_id}", headers=other).status_code == 404


def test_users_cannot_delete_each_others_documents(client, auth_headers):
    doc_id = upload(client, auth_headers).json()["data"]["id"]
    other = second_user(client)

    assert client.delete(f"/documents/{doc_id}", headers=other).status_code == 404
    # still there for the real owner
    assert client.get(f"/documents/{doc_id}", headers=auth_headers).status_code == 200


def test_answers_never_come_from_another_users_documents(client, auth_headers):
    """The single most important test in this file."""
    upload(client, auth_headers)                       # only user A uploads
    other = second_user(client)

    r = client.post(
        "/ask", json={"question": "Where is the office?"}, headers=other
    )
    assert r.status_code == 200
    body = r.json()["data"]

    assert "Norodom" not in body["answer"]
    assert body["sources"] == [] or all(
        "Norodom" not in s["text"] for s in body["sources"]
    )


# --- retrieval -------------------------------------------------------------

def test_ask_uses_uploaded_documents(client, auth_headers):
    upload(client, auth_headers)

    r = client.post(
        "/ask", json={"question": "Where is the office?"}, headers=auth_headers
    )
    assert r.status_code == 200

    body = r.json()["data"]
    assert body["engine"] == "documents"
    assert "Norodom" in body["answer"]


def test_ask_falls_back_to_demo_faqs_without_documents(client, auth_headers):
    r = client.post(
        "/ask", json={"question": "refund policy"}, headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json()["data"]["engine"].endswith("demo-faqs")


def test_deleting_a_document_removes_it_from_answers(client, auth_headers):
    doc_id = upload(client, auth_headers).json()["data"]["id"]

    assert client.delete(f"/documents/{doc_id}", headers=auth_headers).status_code == 200

    r = client.post(
        "/ask", json={"question": "Where is the office?"}, headers=auth_headers
    )
    assert "Norodom" not in r.json()["data"]["answer"]


def test_listing_reports_chunk_totals(client, auth_headers):
    upload(client, auth_headers)
    upload(client, auth_headers, content=b"Just one plain paragraph.", filename="note.md")

    data = client.get("/documents", headers=auth_headers).json()["data"]
    assert data["total"] == 2
    assert data["total_chunks"] == 4      # 3 Q&A pairs + 1 paragraph


# --- pure logic (no HTTP, no database) -------------------------------------

def test_safe_display_name_strips_paths_and_junk():
    assert safe_display_name("../../etc/passwd") == "passwd"
    assert safe_display_name("C:\\Windows\\system32\\evil.txt") == "evil.txt"
    assert safe_display_name("<script>.txt") == "_script_.txt"
    assert safe_display_name("...") == "untitled"
    assert safe_display_name("") == "untitled"


def test_chunk_text_keeps_qa_pairs_together():
    chunks = chunk_text("Q: One?\nA: Yes.\n\nQ: Two?\nA: No.")
    assert len(chunks) == 2
    assert "Q: One?" in chunks[0] and "A: Yes." in chunks[0]


def test_chunk_text_splits_long_prose():
    chunks = chunk_text("word " * 500, size=200, overlap=20)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)
