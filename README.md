# FAQ Chatbot API

A production-shaped REST API in **FastAPI**: JWT authentication with refresh-token
rotation, role-based access control, API keys for machine clients, and a
retrieval-augmented FAQ engine backed by Claude.

**75 tests**, layered architecture, Docker, CI.

```bash
docker build -t faq-api . && docker run -p 8000:8000 faq-api
```

---

## Why this project is interesting

Most tutorial APIs stop at "here is a JWT". This one implements the parts that
actually matter in production:

| | |
|---|---|
| **Revocable sessions** | Access tokens are short-lived JWTs; the long-lived credential is a hashed refresh-token row, so logout genuinely works |
| **Refresh rotation + reuse detection** | Replaying a rotated token revokes every session for that user — a stolen token is usable at most once |
| **Timing-safe login** | An unknown username still burns a real bcrypt verification, so response time cannot reveal which accounts exist |
| **Two auth schemes** | `Authorization: Bearer` for humans, `X-API-Key` for services, resolved by one dependency |
| **Uniform responses** | Every endpoint — success or failure — returns `{success, message, data}`, wired through global exception handlers |
| **Swappable engines** | The FAQ backend is an interface with two implementations, selected by config |

Full engineering notes, including the attack/defence table and what is still
missing before real users: **[docs/PRODUCTION.md](docs/PRODUCTION.md)**.

---

## Stack

FastAPI · Pydantic v2 · SQLAlchemy 2.0 · PyJWT · bcrypt · pytest · Docker
LangChain + Claude + Chroma for the optional RAG engine

---

## Quick start

```bash
python -m venv venv
venv\Scripts\activate          # Windows;  source venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env
```

Start it:

```bash
./dev                          # or: uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/docs>. The admin from `.env` is created on first
boot — log in, copy the `access_token`, click **Authorize**.

Other tasks: `./dev test`, `./dev admin --username you`, `./dev demo`.
On Windows PowerShell use `.\dev` instead of `./dev`.

---

## API

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/auth/register` | — | Create an account |
| `POST` | `/auth/login` | — | Username + password → token pair |
| `POST` | `/auth/refresh` | — | Rotate tokens |
| `POST` | `/auth/logout` | bearer | Revoke one session |
| `POST` | `/auth/logout-all` | bearer | Revoke every session |
| `GET` | `/auth/me` | bearer | Current user |
| `POST` | `/auth/api-keys` | bearer | Mint a machine key (shown once) |
| `DELETE` | `/auth/api-keys/{id}` | bearer | Revoke a key |
| `POST` | `/documents` | bearer or key | Upload + ingest a document |
| `GET` | `/documents` | bearer or key | List your documents |
| `GET` | `/documents/{id}` | bearer or key | One document |
| `DELETE` | `/documents/{id}` | bearer or key | Delete document, chunks, file |
| `POST` | `/ask` | bearer or key | Ask the FAQ bot |
| `GET` | `/faqs` | bearer or key | List / search FAQs |
| `GET` | `/faqs/{id}` | bearer or key | One FAQ |
| `POST` | `/admin/reload` | **admin** | Rebuild the engine |
| `GET` | `/health` | — | Liveness probe |

Every response shares one shape:

```json
{ "success": true, "message": "Login successful", "data": { "access_token": "..." } }
```

```json
{ "success": false, "message": "Incorrect username or password", "data": null,
  "error": { "code": "unauthorized" }, "request_id": "3f2a..." }
```

---

## Layout

```
app/
  main.py              app factory, middleware, global error handling
  api/                 routers           (Spring: @RestController)
  core/
    config.py          typed settings    (@ConfigurationProperties)
    security.py        bcrypt + JWT      (PasswordEncoder + JwtService)
    deps.py            auth dependencies (SecurityFilterChain)
    ratelimit.py
  db/                  SQLAlchemy models (@Entity)
  schemas/             Pydantic DTOs     (DTO + @Valid)
  services/            business logic    (@Service)
tests/                 75 tests
scripts/               admin creation, demo walkthrough, RAG evaluation
```

Services import no web framework, so the same `ensure_admin()` runs from an
HTTP route, a CLI script, and a test.

---

## Document ingestion

Users upload their own knowledge base; answers come from their documents.

```bash
curl -X POST http://127.0.0.1:8000/documents \
  -H "Authorization: Bearer $TOKEN" -F "file=@handbook.md"
```

```
upload → validate → decode → chunk → index → searchable via POST /ask
```

Chunking is section-aware: markdown headings become boundaries and are
prepended to every chunk of their section (the body of "Support hours" rarely
repeats the word "support", so without the heading the section is unfindable).
`Q:/A:` pairs stay intact. Prose is packed with a word-safe overlap.

Upload handling is where the security work is: streamed reads with a byte
counter (never `await file.read()` — that is a one-line DoS), server-generated
UUID paths so a client filename cannot traverse, an extension allowlist, a
binary sniff, per-user quotas, and SHA-256 deduplication. Every document query
filters on `user_id`; `test_answers_never_come_from_another_users_documents`
is the test that matters most in this repo.

### Measured retrieval accuracy

Ranking is **BM25** — IDF, term-frequency saturation, and document-length
normalisation — implemented in `app/services/search.py`.

`scripts/eval_ingestion.py` uploads a realistic 5 KB support handbook
(`samples/`) and scores 20 questions against it:

| Metric | Result |
|---|---|
| **Recall** — fact present in the top 3 chunks | **90%** |
| **Answer** — fact present in the top 1 chunk | **65%** |

Those numbers come from actually running it, and the gap is the point: a RAG
pipeline reads all retrieved chunks, so 90% is the ceiling on generated answer
quality, while 65% is what returning the single best passage verbatim gives
today.

The evaluation earned its place — it caught length-normalisation missing from
the ranking (one long section was answering nearly every question, holding
accuracy at 55%) and a chunker that cut mid-word. Known remaining gap: no
stemming, so "refund" does not match "refunds". See `test_known_limitation_no_stemming`.

## The FAQ engine

Two implementations behind one interface, chosen by `USE_RAG`:

- **`KeywordFaqEngine`** (default) — BM25 over the built-in demo FAQ set, used
  when a user has uploaded nothing yet. No API key, no network, milliseconds.
- **`RagFaqEngine`** — LangChain + Chroma vector search + Claude, with a
  grounded prompt that refuses to answer outside the FAQ corpus.

Set `USE_RAG=true` and `ANTHROPIC_API_KEY` in `.env` to switch. Retrieval and
generation quality can be scored with `scripts/evaluate_rag.py` (LangSmith).

---

## Tests

```bash
./dev test
```

Tests are named after the rule they defend, not the function they call —
`test_reusing_a_rotated_refresh_token_kills_all_sessions`,
`test_user_cannot_revoke_another_users_api_key`,
`test_wrong_password_and_unknown_user_give_identical_errors`.

---

## License

MIT
