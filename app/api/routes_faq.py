"""
Chat endpoints - behind authentication, same response envelope.

The ONLY thing that makes these routes protected is `user: CurrentUser` in the
signature. That one parameter is the whole authorization requirement.
"""

import time
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.core.deps import AdminUser, CurrentUser, DbSession
from app.core.ratelimit import api_limiter
from app.schemas.envelope import ApiResponse, ok
from app.schemas.faq import AskRequest, AskResponse, FaqItem, FaqList
from app.services import retrieval
from app.services.faq_engine import parse_faqs

router = APIRouter(tags=["faq"])


@router.post("/ask", response_model=ApiResponse[AskResponse])
def ask(body: AskRequest, request: Request, user: CurrentUser, db: DbSession):
    """
    Ask the bot. Requires a bearer token or an X-API-Key header.

    Answers come from YOUR uploaded documents when you have any, and fall back
    to the built-in demo FAQ set when you have none - so a new account can try
    the endpoint before uploading anything.

    Rate limited PER USER, not per IP: authenticated traffic should be
    accounted to the account, or one office NAT shares a single bucket.
    """
    api_limiter.check(f"ask:{user.id}")

    started = time.perf_counter()

    if retrieval.user_chunk_count(db, user.id) > 0:
        answer, sources = retrieval.answer_from_documents(
            db, user.id, body.question, body.top_k
        )
        engine_name = "documents"
    else:
        engine = request.app.state.engine   # built once at startup, see main.py
        answer, sources = engine.ask(body.question, body.top_k)
        engine_name = f"{engine.name}:demo-faqs"

    took_ms = int((time.perf_counter() - started) * 1000)

    payload = AskResponse(
        question=body.question,
        answer=answer,
        sources=sources,
        engine=engine_name,
        took_ms=took_ms,
    )

    # "success" means the REQUEST worked. Finding no matching FAQ is a valid
    # answer, not a failure - so this stays success=true with a clear message.
    # Do not conflate "the call failed" with "the result was empty".
    message = "Answer found" if sources else "No matching FAQ found"
    return ok(payload, message)


@router.get("/faqs", response_model=ApiResponse[FaqList])
def list_faqs(
    user: CurrentUser,
    search: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    items = [
        {"id": i, "question": q, "answer": a}
        for i, (q, a) in enumerate(parse_faqs())
    ]

    if search:
        needle = search.lower()
        items = [
            it for it in items if needle in (it["question"] + it["answer"]).lower()
        ]

    return ok(
        {"total": len(items), "items": items[:limit]},
        f"{len(items)} FAQ(s) found",
    )


@router.get("/faqs/{faq_id}", response_model=ApiResponse[FaqItem])
def get_faq(faq_id: int, user: CurrentUser):
    pairs = parse_faqs()

    if faq_id < 0 or faq_id >= len(pairs):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No FAQ with id {faq_id}")

    q, a = pairs[faq_id]
    return ok({"id": faq_id, "question": q, "answer": a})


@router.post(
    "/admin/reload",
    response_model=ApiResponse[None],
    status_code=status.HTTP_202_ACCEPTED,
)
def reload_engine(request: Request, admin: AdminUser):
    """
    Admin-only. `admin: AdminUser` is the whole @PreAuthorize("hasRole('ADMIN')").
    A non-admin gets 403 and this function body never runs.
    """
    from app.core.config import get_settings
    from app.services.faq_engine import build_engine

    request.app.state.engine = build_engine(get_settings().use_rag)
    return ok(message=f"Engine reloaded with {request.app.state.engine.count()} FAQs")
