"""
Auth endpoints.

Every handler returns the same envelope:
    { "success": bool, "message": str, "data": ... }

JAVA: an @RestController returning ResponseEntity<ApiResponse<T>>.
"""

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession, get_client_ip
from app.core.ratelimit import login_limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    generate_api_key,
    hash_password,
    hash_token,
    verify_password,
)

# hash_password is still used below for the timing-attack decoy hash.
from app.db.models import ApiKey, RefreshToken, User
from app.schemas.auth import (
    ApiKeyCreate,
    ApiKeyOut,
    LoginRequest,
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserOut,
)
from app.schemas.envelope import ApiResponse, ok
from app.services.user_service import (
    UsernameAlreadyExists,
    create_user,
    get_by_username,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# A real bcrypt hash of a random string. Used to burn the same ~250ms when the
# username does not exist, so an attacker cannot tell "no such user" from
# "wrong password" by timing the response.
_DUMMY_HASH = hash_password("timing-attack-decoy-Password1")


def _issue_tokens(db, user: User) -> TokenPair:
    """Create an access token + a stored, revocable refresh token."""
    raw_refresh, refresh_hash, expires_at = create_refresh_token()

    db.add(RefreshToken(user_id=user.id, token_hash=refresh_hash, expires_at=expires_at))
    db.commit()

    return TokenPair(
        access_token=create_access_token(subject=str(user.id), role=user.role),
        refresh_token=raw_refresh,
        expires_in=get_settings().access_token_minutes * 60,
    )


@router.post(
    "/register",
    response_model=ApiResponse[UserOut],
    status_code=status.HTTP_201_CREATED,
)
def register(payload: UserCreate, db: DbSession):
    """
    Create an account.

    In a real product this is either invite-only, admin-only, or protected by
    a CAPTCHA. Open registration on a public API is how you end up hosting
    someone else's spam.
    """
    try:
        # Note the role is hardcoded to "user" and never read from the request.
        # If clients could pass a role, anyone could register as an admin -
        # this is called mass assignment, and it is a classic way to lose a
        # system. Admins are created only by scripts/create_admin.py or the
        # ADMIN_USERNAME/ADMIN_PASSWORD seed.
        user = create_user(db, payload.username, payload.password, role="user")
    except UsernameAlreadyExists:
        # This DOES confirm which usernames exist - but unlike an email, a
        # username is public by design (it shows on posts, profiles, etc.), and
        # a signup form has to tell you the name is taken. So the tradeoff that
        # mattered for emails does not apply here.
        # `from None` hides the internal exception from the traceback we log.
        # Without it Python chains them ("During handling of the above
        # exception..."), which is noise here - the 409 IS the whole story.
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Username already taken"
        ) from None

    # `user` is a SQLAlchemy row; response_model=ApiResponse[UserOut] converts
    # it and drops everything not on UserOut - including the password hash.
    return ok(user, "Account created successfully")


@router.post("/login", response_model=ApiResponse[TokenPair])
def login(payload: LoginRequest, request: Request, db: DbSession):
    """
    Exchange username + password for a token pair. Plain JSON body.

    JAVA: @PostMapping("/login") public ApiResponse<TokenPair> login(@RequestBody ...)
    """
    login_limiter.check(f"login:{get_client_ip(request)}")

    # get_by_username normalizes case, so "Admin" and "admin" both work.
    user = get_by_username(db, payload.username)

    if user is None:
        verify_password(payload.password, _DUMMY_HASH)   # constant-ish time
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Incorrect username or password"
        )

    if not verify_password(payload.password, user.hashed_password):
        # Same message for both failures. Even though usernames are public,
        # keep the responses identical: a distinct "no such user" reply turns
        # the login form into a free account-existence oracle for scripts.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Incorrect username or password"
        )

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

    login_limiter.reset(f"login:{get_client_ip(request)}")
    return ok(_issue_tokens(db, user), "Login successful")


@router.post("/refresh", response_model=ApiResponse[TokenPair])
def refresh(payload: RefreshRequest, db: DbSession):
    """
    Trade a refresh token for a new pair. The old one is revoked immediately
    (rotation), so a stolen token is usable at most once.
    """
    token_hash = hash_token(payload.refresh_token)
    record = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    ).scalar_one_or_none()

    if record is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    if record.revoked:
        # Reuse of an already-rotated token means it leaked. Kill every session
        # for that user and force a fresh login.
        db.query(RefreshToken).filter(RefreshToken.user_id == record.user_id).update(
            {"revoked": True}
        )
        db.commit()
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Refresh token reuse detected - all sessions revoked",
        )

    if not record.is_usable():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token expired")

    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User unavailable")

    record.revoked = True          # rotate
    db.add(record)
    return ok(_issue_tokens(db, user), "Token refreshed")


@router.post("/logout", response_model=ApiResponse[None])
def logout(payload: RefreshRequest, db: DbSession, user: CurrentUser):
    """
    Revoke one refresh token.

    Returns 200 with a message rather than 204 No Content: 204 means "no body",
    so it cannot carry a success message. Consistency beats HTTP purity here.

    The current ACCESS token still works until it expires - that is inherent to
    JWTs. Keep access-token lifetime short (15 min) and this is acceptable. If
    you truly need instant kill, you need a deny-list in Redis checked on every
    request, which gives up most of the reason to use JWTs at all.
    """
    db.query(RefreshToken).filter(
        RefreshToken.token_hash == hash_token(payload.refresh_token),
        RefreshToken.user_id == user.id,        # cannot revoke someone else's
    ).update({"revoked": True})
    db.commit()
    return ok(message="Logged out")


@router.post("/logout-all", response_model=ApiResponse[None])
def logout_all(db: DbSession, user: CurrentUser):
    """Revoke every session - the 'sign out of all devices' button."""
    count = (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False))
        .update({"revoked": True})
    )
    db.commit()
    return ok(message=f"Logged out of {count} session(s)")


@router.get("/me", response_model=ApiResponse[UserOut])
def me(user: CurrentUser):
    """JAVA: @AuthenticationPrincipal UserDetails principal"""
    return ok(user)


@router.post(
    "/api-keys",
    response_model=ApiResponse[ApiKeyOut],
    status_code=status.HTTP_201_CREATED,
)
def create_api_key(payload: ApiKeyCreate, db: DbSession, user: CurrentUser):
    """Mint a machine credential. The raw key is returned exactly once."""
    raw, key_hash = generate_api_key()

    record = ApiKey(user_id=user.id, name=payload.name, key_hash=key_hash)
    db.add(record)
    db.commit()
    db.refresh(record)

    return ok(
        ApiKeyOut(id=record.id, name=record.name, key=raw),
        "API key created - copy it now, it will not be shown again",
    )


@router.delete("/api-keys/{key_id}", response_model=ApiResponse[None])
def revoke_api_key(key_id: int, db: DbSession, user: CurrentUser):
    updated = (
        db.query(ApiKey)
        .filter(ApiKey.id == key_id, ApiKey.user_id == user.id)
        .update({"is_active": False})
    )
    db.commit()

    # Without the user_id filter above, any user could revoke any key.
    # That class of bug (IDOR) is the most common real-world API vulnerability.
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")

    return ok(message="API key revoked")
