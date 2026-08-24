r"""
Measure retrieval accuracy on a real document.

    .\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
    .\venv\Scripts\python.exe scripts\eval_ingestion.py

Uploads samples/clouddesk_support_handbook.md, asks a fixed set of questions,
and checks whether the expected fact appears in the answer.

Two scores are reported, and the gap between them is the interesting part:

  ANSWER  - the fact is in the top-ranked chunk (what the user actually sees)
  RECALL  - the fact is in ANY returned chunk (what an LLM would receive)

A RAG pipeline reads all the returned chunks, so RECALL is the ceiling on how
good generated answers could be. ANSWER is what this keyword engine delivers
today. If RECALL is high and ANSWER is low, the retrieval works and only the
ranking needs improvement.
"""

import sys
from pathlib import Path

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
DOC = Path(__file__).resolve().parents[1] / "samples" / "clouddesk_support_handbook.md"
USERNAME = "eval_runner"
PASSWORD = "EvalRunnerPass1"
TOP_K = 3

# (question, phrase that must appear for the answer to be correct)
CASES: list[tuple[str, str]] = [
    ("How much does the Business plan cost?", "$49"),
    ("What is the seat limit on the Starter plan?", "5 seats"),
    ("How much storage does Business include?", "100 GB"),
    ("Is there a discount for paying annually?", "20 percent"),
    ("Which credit cards do you accept?", "Mastercard"),
    ("What happens when a card payment fails?", "read-only"),
    ("How long is data kept after a downgrade?", "60 days"),
    ("Can I get a refund on a monthly plan?", "not refunded"),
    ("How long do refunds take to arrive?", "5 to 10"),
    ("How much can a support agent refund without approval?", "$500"),
    ("How long is a password reset link valid?", "60 minutes"),
    ("Do you support SMS two factor authentication?", "SIM"),
    ("Which SSO providers are supported?", "Okta"),
    ("Where is EU customer data stored?", "Frankfurt"),
    ("How long until deleted data is purged from backups?", "35 days"),
    ("What is the API rate limit on Starter?", "60 requests"),
    ("What status code do I get when rate limited?", "429"),
    ("When does support close?", "6pm"),
    ("Who do I contact about a total outage?", "PagerDuty"),
    ("How long does an export download link last?", "7 days"),
]


def main() -> None:
    if not DOC.exists():
        sys.exit(f"Missing sample document: {DOC}")

    with httpx.Client(base_url=BASE, timeout=60) as c:
        c.post("/auth/register", json={"username": USERNAME, "password": PASSWORD})
        login = c.post(
            "/auth/login", json={"username": USERNAME, "password": PASSWORD}
        )
        if login.status_code != 200:
            sys.exit(f"Login failed: {login.text}")

        auth = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}

        # Start clean so a re-run measures this document only.
        for doc in c.get("/documents", headers=auth).json()["data"]["items"]:
            c.delete(f"/documents/{doc['id']}", headers=auth)

        upload = c.post(
            "/documents",
            files={"file": (DOC.name, DOC.read_bytes(), "text/markdown")},
            headers=auth,
        )
        if upload.status_code != 201:
            sys.exit(f"Upload failed: {upload.text}")

        meta = upload.json()["data"]
        print(f"\nIngested {meta['filename']}: "
              f"{meta['size_bytes']} bytes -> {meta['chunk_count']} chunks\n")
        print(f"{'':2} {'question':<52} {'answer':<8} recall")
        print("-" * 78)

        answer_hits = recall_hits = 0

        for i, (question, expected) in enumerate(CASES, 1):
            r = c.post(
                "/ask",
                json={"question": question, "top_k": TOP_K},
                headers=auth,
            )
            data = r.json()["data"]

            in_answer = expected.lower() in data["answer"].lower()
            in_sources = any(
                expected.lower() in s["text"].lower() for s in data["sources"]
            )

            answer_hits += in_answer
            recall_hits += in_sources

            print(f"{i:>2} {question[:50]:<52} "
                  f"{'HIT ' if in_answer else 'miss':<8} "
                  f"{'HIT' if in_sources else 'miss'}")

            if not in_sources:
                got = data["answer"][:70].replace("\n", " ")
                print(f"{'':2} {'  expected: ' + expected:<52} got: {got}")

        total = len(CASES)
        print("-" * 78)
        print(f"ANSWER accuracy (top chunk) : {answer_hits}/{total}"
              f"  ({answer_hits / total:.0%})")
        print(f"RECALL  (any of top {TOP_K})     : {recall_hits}/{total}"
              f"  ({recall_hits / total:.0%})")

        # Leave nothing behind.
        for doc in c.get("/documents", headers=auth).json()["data"]["items"]:
            c.delete(f"/documents/{doc['id']}", headers=auth)


if __name__ == "__main__":
    main()
