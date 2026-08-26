"""
Shared constants.

WHY THIS FILE EXISTS
--------------------
"Magic" strings and numbers scattered across the code are easy to mistype and
hard to change - rename one and you have to hunt down every copy. Defining them
ONCE here means there is a single source of truth.

    JAVA: a `public final class ErrorCodes { ... }` of constants.

WHAT'S AN "ERROR CODE" HERE?
----------------------------
Two different things share the phrase, so keep them straight:

- HTTP status code  -> a NUMBER like 404. FastAPI already gives these friendly
                       names (`status.HTTP_404_NOT_FOUND`), so we reuse those
                       rather than inventing our own.
- API error code    -> a stable STRING like "not_found" that we put in the JSON
                       error envelope: {"error": {"code": "not_found"}}. Clients
                       read this instead of parsing human text, so it is part of
                       your public contract - renaming one is a breaking change.
"""

from fastapi import status

# --- API error-code strings --------------------------------------------------
# Naming each string as a constant means the type checker / editor catches a
# typo like NOT_FUOND, whereas a bare "not_fuond" string would slip through.
BAD_REQUEST = "bad_request"
UNAUTHORIZED = "unauthorized"
FORBIDDEN = "forbidden"
NOT_FOUND = "not_found"
CONFLICT = "conflict"
FILE_TOO_LARGE = "file_too_large"
UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
VALIDATION_ERROR = "validation_error"
RATE_LIMITED = "rate_limited"
INTERNAL_ERROR = "internal_error"
SERVICE_UNAVAILABLE = "service_unavailable"

# Fallback code used when a status has no specific entry in the map below.
DEFAULT_ERROR_CODE = "error"

# --- HTTP status code -> API error-code string -------------------------------
# Built from FastAPI's own named status constants, so there are no bare numbers
# (like 404) hardcoded here either.
STATUS_TO_ERROR_CODE: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: BAD_REQUEST,
    status.HTTP_401_UNAUTHORIZED: UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN: FORBIDDEN,
    status.HTTP_404_NOT_FOUND: NOT_FOUND,
    status.HTTP_409_CONFLICT: CONFLICT,
    status.HTTP_413_CONTENT_TOO_LARGE: FILE_TOO_LARGE,
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: UNSUPPORTED_MEDIA_TYPE,
    status.HTTP_422_UNPROCESSABLE_CONTENT: VALIDATION_ERROR,
    status.HTTP_429_TOO_MANY_REQUESTS: RATE_LIMITED,
    status.HTTP_500_INTERNAL_SERVER_ERROR: INTERNAL_ERROR,
    status.HTTP_503_SERVICE_UNAVAILABLE: SERVICE_UNAVAILABLE,
}
