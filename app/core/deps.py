"""
The dependency chain - this is where authentication actually happens.

JAVA: this file replaces your whole Spring Security filter chain +
      UserDetailsService + @PreAuthorize.

The idea: each dependency is a small function. FastAPI runs them before your
handler, in order, and injects the results. If one raises HTTPException, the
handler never runs.

    request -> get_bearer_token -> get_current_user -> require_active -> handler
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import TokenError, decode_access_token, hash_token
from app.db.database import get_db
from app.db.models import ApiKey, User

# HTTPBearer = "read the Authorization: Bearer <token> header". Nothing else.
#
# We deliberately do NOT use OAuth2PasswordBearer here. It makes Swagger show a
# username/password/client_id/client_secret dialog, but client_id and
# client_secret belong to a DIFFERENT OAuth flow that this API does not
# implement - so those two boxes are pure confusion. With HTTPBearer the
# Authorize dialog is one box: paste your access_token.
#
# auto_error=False -> we handle a missing header ourselves, so a request can
# authenticate with EITHER a bearer token or an API key.
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Paste the access_token returned by POST /auth/login",
)
api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        # required by the spec; tells the client how to authenticate
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    db: DbSession,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
    api_key: Annotated[str | None, Security(api_key_scheme)] = None,
) -> User:
    """
    JAVA: the JwtAuthenticationFilter that populates the SecurityContext.

    Accepts either:
      Authorization: Bearer <jwt>     (humans / web app)
      X-API-Key: faq_xxx              (other services)
    """
    user: User | None = None
    token = creds.credentials if creds else None   # the part after "Bearer "

    if token:
        try:
            payload = decode_access_token(token)
        except TokenError as e:
            raise _unauthorized(str(e)) from e

        user_id = payload.get("sub")
        if user_id is None:
            raise _unauthorized("Malformed token")

        user = db.get(User, int(user_id))

    elif api_key:
        # look up by HASH - the raw key is never stored, so a DB leak is useless
        stmt = select(ApiKey).where(
            ApiKey.key_hash == hash_token(api_key),
            ApiKey.is_active.is_(True),
        )
        record = db.execute(stmt).scalar_one_or_none()
        if record:
            user = db.get(User, record.user_id)

    if user is None:
        raise _unauthorized("Not authenticated")

    if not user.is_active:
        # 403 not 401: we know who you are, you just may not do this
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*allowed: str):
    """
    JAVA: @PreAuthorize("hasRole('ADMIN')")

    A dependency FACTORY: call it to build a dependency.
    Usage:  @router.get("/admin", dependencies=[Depends(require_role("admin"))])
       or:  def handler(user: Annotated[User, Depends(require_role("admin"))])
    """

    def checker(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Requires one of these roles: {', '.join(allowed)}",
            )
        return user

    return checker


AdminUser = Annotated[User, Depends(require_role("admin"))]


def get_client_ip(request: Request) -> str:
    """
    Behind nginx / a load balancer, request.client.host is the PROXY's IP.
    Only trust X-Forwarded-For if your proxy sets it and strips client-supplied
    values - otherwise anyone can spoof their way past a rate limiter.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
