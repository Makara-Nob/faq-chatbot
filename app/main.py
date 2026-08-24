r"""
Application entry point.

JAVA: @SpringBootApplication class + WebSecurityConfig + WebMvcConfig,
      all in one small file.

Run:
    .\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import routes_auth, routes_documents, routes_faq
from app.core.config import get_settings
from app.db.database import Base, SessionLocal
from app.db.database import engine as db_engine
from app.schemas.auth import UserCreate
from app.schemas.envelope import ApiResponse, ErrorResponse, ok
from app.schemas.faq import HealthResponse
from app.services.faq_engine import build_engine
from app.services.user_service import ensure_admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("faq-api")

settings = get_settings()


def seed_admin_from_settings() -> None:
    """
    Create (or promote) the admin named in .env - ADMIN_USERNAME + ADMIN_PASSWORD.

    JAVA: a CommandLineRunner guarded by @Profile("dev").

    Idempotent: on later boots it only promotes, and never overwrites the
    password. So editing ADMIN_PASSWORD in .env will NOT change an existing
    account - use `dev admin --username ... --reset-password` for that. That is
    deliberate: a config file silently rewriting a live credential on every
    restart is a bad surprise.
    """
    if not settings.seed_admin:
        return

    if not (settings.admin_username and settings.admin_password):
        log.info("no ADMIN_USERNAME/ADMIN_PASSWORD in config - skipping admin seed")
        return

    try:
        # Same rules as public registration - a seeded admin must not be
        # allowed a weaker password than a normal user.
        UserCreate(username=settings.admin_username, password=settings.admin_password)
    except ValidationError as e:
        # Do not crash the app over a bad seed value; log it and move on.
        reasons = "; ".join(err["msg"] for err in e.errors())
        log.error(
            "admin seed skipped - invalid ADMIN_USERNAME/ADMIN_PASSWORD: %s", reasons
        )
        return

    if settings.is_prod:
        log.warning(
            "seeding an admin from environment config in PRODUCTION - prefer a "
            "secrets manager plus scripts/create_admin.py as a deploy step"
        )

    with SessionLocal() as db:
        user, created = ensure_admin(
            db, settings.admin_username, settings.admin_password
        )

    log.info(
        "admin %s: %s (role=%s)",
        "created" if created else "already present",
        user.username,
        user.role,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # JAVA: @PostConstruct / ApplicationRunner
    #
    # create_all is fine for dev/demo. In production use Alembic migrations:
    #   alembic revision --autogenerate -m "add users"
    #   alembic upgrade head
    # (Alembic is Flyway. Never let an app auto-mutate a production schema.)
    Base.metadata.create_all(bind=db_engine)

    seed_admin_from_settings()

    app.state.engine = build_engine(settings.use_rag)
    log.info("started env=%s engine=%s faqs=%d",
             settings.env, app.state.engine.name, app.state.engine.count())

    yield

    db_engine.dispose()
    log.info("shutdown complete")


app = FastAPI(
    title="FAQ Chatbot API",
    version="2.0.0",
    lifespan=lifespan,
    # Do not publish your API surface to the internet in production.
    docs_url=None if settings.is_prod else "/docs",
    redoc_url=None if settings.is_prod else "/redoc",
    openapi_url=None if settings.is_prod else "/openapi.json",
)


# ---------------------------------------------------------------------------
# Middleware. NOTE: middleware runs bottom-up - the LAST one added is the
# OUTERMOST. Order matters when one depends on another.
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,   # never ["*"] together with credentials
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """
    JAVA: a Filter that puts a correlation id in the MDC.

    Every log line and every error response carries the same request id, so a
    user can send you "request 3f2a..." and you can find it instantly.
    """
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id

    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed = (time.perf_counter() - started) * 1000
        log.exception("request_id=%s %s %s failed after %.1fms",
                      request_id, request.method, request.url.path, elapsed)
        raise

    elapsed = (time.perf_counter() - started) * 1000
    log.info("request_id=%s %s %s -> %d %.1fms", request_id, request.method,
             request.url.path, response.status_code, elapsed)

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = f"{elapsed:.1f}"

    # Cheap, high-value security headers.
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if settings.is_prod:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


# ---------------------------------------------------------------------------
# Global error handling  (JAVA: @ControllerAdvice)
#
# These three handlers are what guarantee that EVERY failure comes back in the
# same envelope as every success. Without them, FastAPI's defaults would return
# {"detail": ...} and the client would need a second code path.
# ---------------------------------------------------------------------------

_ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    413: "file_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    503: "service_unavailable",
}


def _fail(request: Request, code: int, message: str, **extra) -> JSONResponse:
    body = ErrorResponse(
        message=message,
        error={"code": _ERROR_CODES.get(code, "error"), **extra},
        request_id=getattr(request.state, "request_id", None),
    )
    return JSONResponse(status_code=code, content=body.model_dump())


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    """
    Catches every `raise HTTPException(...)` in the app and re-wraps it.
    `exc.detail` is the message the handler passed in.
    """
    response = _fail(request, exc.status_code, str(exc.detail))

    # Preserve auth/rate-limit headers - WWW-Authenticate and Retry-After are
    # part of the protocol, and dropping them here would silently break clients.
    for key, value in (exc.headers or {}).items():
        response.headers[key] = value

    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    """
    Pydantic rejected the input (422). We flatten its error list into
    {"username": "String should match pattern ..."} so a form can show the
    message under the right field.

    JAVA: MethodArgumentNotValidException -> getBindingResult().getFieldErrors()
    """
    fields = {}
    for err in exc.errors():
        # loc looks like ("body", "password") - skip the first segment
        name = ".".join(str(p) for p in err["loc"][1:]) or "body"
        fields[name] = err["msg"]

    first = next(iter(fields.values()), "Invalid request")
    return _fail(request, 422, first, fields=fields)


@app.exception_handler(FileNotFoundError)
async def missing_data(request: Request, exc: FileNotFoundError):
    log.error("data file missing: %s", exc)
    return _fail(request, 503, "FAQ data is unavailable")


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    """
    The single most important production rule in this file:
    NEVER return a stack trace to the client. Log the detail, return an id.
    """
    log.exception("request_id=%s unhandled error",
                  getattr(request.state, "request_id", "unknown"))

    return _fail(
        request, 500, "Something went wrong. Quote the request_id to support."
    )


# ---------------------------------------------------------------------------
# Routers  (JAVA: component scanning finds your @RestControllers; here it is
#           explicit, which means you can always see the whole API surface)
# ---------------------------------------------------------------------------

app.include_router(routes_auth.router)
app.include_router(routes_documents.router)
app.include_router(routes_faq.router)


@app.get("/health", response_model=ApiResponse[HealthResponse], tags=["system"])
def health(request: Request):
    """
    Deliberately UNAUTHENTICATED - your load balancer and Kubernetes probe it.
    Keep it cheap and leak nothing sensitive.
    """
    engine = request.app.state.engine
    return ok(
        HealthResponse(status="ok", engine=engine.name, faq_count=engine.count()),
        "Service is healthy",
    )
