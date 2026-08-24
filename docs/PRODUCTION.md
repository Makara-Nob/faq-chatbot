# Production readiness

What is built, what it maps to in Spring, and what is still missing.

---

## Response format

Every endpoint — success or failure — returns the same three keys.

```json
{ "success": true,  "message": "Login successful", "data": { "access_token": "..." } }
```

```json
{ "success": false, "message": "Incorrect email or password", "data": null,
  "error": { "code": "unauthorized" }, "request_id": "3f2a..." }
```

Validation failures name the offending fields, so a form can show each message
in the right place:

```json
{ "success": false, "message": "value is not a valid email address",
  "error": { "code": "validation_error",
             "fields": { "email": "value is not a valid email address",
                         "password": "String should have at least 12 characters" } } }
```

Built from `app/schemas/envelope.py` (`ApiResponse[T]`, the `ok()` helper) plus
three exception handlers in `app/main.py`. The handlers are the important half:
without them FastAPI returns its own `{"detail": ...}` shape and the client
needs a second code path.

Two rules the code follows:

- **The HTTP status still carries the truth.** The envelope is for humans and
  for lazy clients; `success: false` always comes with a 4xx/5xx. Never return
  `200 {"success": false}` — every proxy, retry policy and monitoring tool reads
  the status code, not your body.
- **`success` means the request worked, not that the result was interesting.**
  Asking a question with no matching FAQ is `success: true` with the message
  "No matching FAQ found". Empty is not an error.

## Auth design (the part you asked about)

```
POST /auth/register   -> create account (bcrypt hash, never the password)
POST /auth/login      -> email + password (JSON)  =>  access + refresh token
POST /auth/refresh    -> rotate: old token dies, new pair issued
POST /auth/logout     -> revoke one refresh token
POST /auth/logout-all -> revoke every session
GET  /auth/me         -> current user
POST /auth/api-keys   -> mint a machine credential (shown once)
```

Login is by **username**, not email:

```json
POST /auth/login   { "username": "admin", "password": "..." }
```

Username rules — 3–50 characters, `a-z A-Z 0-9 . _ -` only. Two deliberate
choices behind that:

- **Stored and compared lowercase** (`normalize_username`, applied on write
  *and* on lookup). Otherwise `Admin` and `admin` become two accounts, and a
  user who capitalises at login can never get in.
- **ASCII only.** Unicode would let someone register `аdmin` with a Cyrillic
  `а` and impersonate `admin` visually. Homograph attacks are cheap to block
  here and painful to fix later.

Authenticate with either header:

```
Authorization: Bearer <access_token>
X-API-Key: faq_xxxxxxxx
```

The Swagger **Authorize** dialog is a single box — paste the `access_token`.
It uses `HTTPBearer`, not `OAuth2PasswordBearer`: the latter renders
username/password/client_id/client_secret fields, and `client_id`/`client_secret`
belong to a different OAuth flow this API does not implement. Two confusing
boxes that do nothing is worse than no dialog at all.

Two token types, on purpose:

| | Access token (JWT) | Refresh token (random string) |
|---|---|---|
| Stored server-side? | no | yes, as SHA-256 |
| Lifetime | 15 min | 7 days |
| Revocable? | **no** | yes - delete the row |
| Sent on | every request | only to `/auth/refresh` |

This is the whole trick. A JWT cannot be revoked, so it must be short-lived.
The long-lived credential is a database row you can delete — that is what makes
logout real.

**Rotation + reuse detection.** Every refresh issues a new refresh token and
revokes the old one. If a revoked one is presented again, that means it leaked,
so every session for that user is killed. Most tutorials skip this; it is the
difference between a demo and something you can operate.

### Spring Security mapping

| Spring | Here |
|---|---|
| `SecurityFilterChain` config | `app/core/deps.py` |
| `JwtAuthenticationFilter` | `get_current_user()` |
| `UserDetailsService` | the `db.get(User, id)` inside it |
| `@PreAuthorize("hasRole('ADMIN')")` | `require_role("admin")` |
| `@AuthenticationPrincipal` | `user: CurrentUser` in the signature |
| `BCryptPasswordEncoder` | `app/core/security.py` |
| `AuthenticationEntryPoint` | `_unauthorized()` |

Adding auth to any endpoint is one parameter:

```python
def ask(body: AskRequest, user: CurrentUser):   # 401 if not logged in
def reload(admin: AdminUser):                   # 403 if not admin
```

### Attacks this code specifically defends against

| Attack | Defence | Where |
|---|---|---|
| Password DB leak | bcrypt, cost 12 | `security.hash_password` |
| Token DB leak | only SHA-256 stored | `security.hash_token` |
| User enumeration by response | identical 401 message | `routes_auth.login` |
| Homograph impersonation (`аdmin`) | ASCII-only username pattern | `schemas/auth.Username` |
| Case-variant duplicate accounts | lowercase on write and lookup | `normalize_username` |
| User enumeration by **timing** | dummy hash when user missing | `_DUMMY_HASH` |
| Credential stuffing | 5 logins/min per IP | `ratelimit.login_limiter` |
| Refresh token theft | rotation + reuse detection | `routes_auth.refresh` |
| Refresh used as access token | `type` claim checked | `decode_access_token` |
| IDOR (revoking someone else's key) | `user_id` in the WHERE clause | `revoke_api_key` |
| Mass assignment (`"role": "admin"`) | role hardcoded, not from the body | `routes_auth.register` |
| Seed credentials in git | password only in the operator's terminal | `scripts/create_admin.py` |
| Stack traces leaked to clients | global handler returns a request id | `main.unhandled_exception` |
| Password hash leaked in a response | separate `UserOut` model | `schemas/auth.py` |
| Timing leak comparing secrets | `secrets.compare_digest` | `constant_time_equals` |

Each one has a test in `tests/`. 75 tests, all passing.

---

## The other five things "production ready" means

**1. Config** — `app/core/config.py`. Typed, validated at startup, from env
vars. It refuses to boot in `prod` with the default secret key. Secrets come
from the environment (AWS Secrets Manager / Vault / your platform), never git.

**2. Database + migrations** — SQLAlchemy 2.0. `create_all()` in `lifespan` is
for dev only. In production use Alembic (= Flyway):

```bash
alembic init migrations
alembic revision --autogenerate -m "add users"
alembic upgrade head
```

Run `upgrade head` as a deploy step, not from the app.

**3. Observability** — every request gets an `X-Request-ID`, echoed in the
response header and in every log line. Errors return that id instead of a
stack trace, so a user report is traceable. Next step: structured JSON logs +
Sentry + `prometheus-fastapi-instrumentator` for metrics.

**4. Error handling** — global handler in `main.py`. The rule: log everything
internally, return nothing internal.

**5. Deployment** — `Dockerfile`: multi-stage, non-root user, layer-cached
deps, healthcheck, 4 uvicorn workers. Workers are **processes** — the GIL means
threads will not use your other cores. Terminate TLS at nginx/ALB, not here.

---

## Still missing before real users

Ordered by how much it will hurt you.

1. **HTTPS** — tokens in plain HTTP are tokens given away. Non-negotiable.
2. **Email verification + password reset** — needs an email provider and
   single-use, expiring, hashed tokens (same pattern as refresh tokens).
3. **Rate limiting in Redis** — the in-memory limiter is per-process, so 4
   workers = 4x your configured limit. `slowapi`, or do it at nginx.
4. **PostgreSQL** — SQLite does not do concurrent writes. Change
   `DATABASE_URL`, add `psycopg[binary]`, done.
5. **Where the frontend stores the token** — `localStorage` is readable by any
   XSS. Prefer an httpOnly, Secure, SameSite cookie for the refresh token.
6. **Account lockout after N failures**, and an audit log of logins.
7. **Cost control on `/ask`** — with `USE_RAG=true` every request costs money.
   Per-user quotas, not just rate limits.
8. **CI** — run `pytest`, `ruff check`, `mypy app` on every push.
9. **Backups**, tested restores, and an alert when the error rate rises.

---

## Creating the first admin

`/auth/register` always creates a plain `user` — the role is hardcoded
server-side and never read from the request body. Admins come from config or
from a script.

### Dev: from `.env` (automatic)

```
ADMIN_USERNAME=admin
ADMIN_PASSWORD=AdminPassword123
SEED_ADMIN=true
```

The app creates or promotes this account at startup — start the server and the
admin exists. `SEED_ADMIN=false` turns it off; the test suite sets that so
tests never inherit your local admin.

Two behaviours to know:

- **Editing `ADMIN_PASSWORD` does not change an existing admin.** The seed only
  ever creates or promotes. A config file that silently rewrites a live
  credential on every restart is a bad surprise. To actually change it, use
  `--reset-password` below, or delete `app.db` and let it rebuild.
- **A bad value does not crash the app.** An invalid email or a too-weak
  password is logged and skipped, so a typo in `.env` cannot take down boot.

The seeded password is validated by the same `UserCreate` rules as public
registration, so a seeded admin cannot be weaker than a normal user.

> In production, leave `ADMIN_PASSWORD` empty. A fixed password in a file on
> disk is a credential anyone with read access owns. Keep the secret in a
> secrets manager and run the script below as a one-off deploy step.

### Anywhere: the script

```bash
python scripts/create_admin.py --username admin
```

Prompts for the password with hidden input, so it never lands in your shell
history. Other modes:

| Situation | Command |
|---|---|
| Interactive terminal | `--username you` |
| No TTY (CI, docker) | `--generate` (prints the password once) |
| Automated | `ADMIN_USERNAME=... ADMIN_PASSWORD=...` (also read from `.env`) |
| Lost the password | `--username you --reset-password` |

Properties worth knowing:

- **Idempotent.** A second run promotes the existing account instead of
  failing, and **never resets the password** — a seed script that overwrites a
  password on every deploy is how you lock yourself out, or hand the account
  to whoever knows the old seed value.
- Also re-enables the account if it was disabled.
- The password is validated by the **same** `UserCreate` rules as public
  registration. A seeded admin cannot be weaker than a normal user.
- Nothing is hardcoded, so no credential ever enters git.

Logic lives in `app/services/user_service.py` (`ensure_admin`), so it is
callable from a route, a test, or the CLI. The script is a thin wrapper.

To promote someone later, run the same command with their email.

## Commands

Use `dev.cmd` — it points at the venv for you, so nothing needs activating.

| | |
|---|---|
| `dev` | start the API with auto-reload |
| `dev test` | run the test suite |
| `dev admin --email you@example.com` | create or promote an admin |
| `dev demo` | walk the whole auth flow |
| `dev install` | install dependencies |
| `dev shell` | Python REPL with `app` importable |

Extra arguments pass straight through: `dev run --port 9000`, `dev test -k admin`.

```bash
cd D:\WORK\faq-chatbot && .\dev
```

The long form still works, and is what you would use in a Dockerfile or a
systemd unit:

```bash
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

`--port 8000` is uvicorn's default, so it never needed to be typed.

Prefer activating the venv instead? Do it once per terminal and both `python`
and `uvicorn` resolve from the venv for the rest of the session:

```bash
.\venv\Scripts\Activate.ps1
```

`api_server.py` is untouched — keep it as the single-file lesson. `app/` is the
production version.
