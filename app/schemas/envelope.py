"""
One response shape for the whole API.

Every response - success or failure - looks like this:

    {
      "success": true,
      "message": "Login successful",
      "data": { ... }            <- null on failure
    }

    {
      "success": false,
      "message": "Incorrect username or password",
      "data": null,
      "error": { "code": "unauthorized" },
      "request_id": "3f2a..."
    }

JAVA: the ApiResponse<T> wrapper class you have written on every Spring
      project, plus the @ControllerAdvice that produces the failure version.

Why bother: the client writes ONE handler. `if (!res.success) showError(res.message)`
- no guessing whether this endpoint returns {detail}, {error}, or a bare object.
"""

from pydantic import BaseModel, Field


class ApiResponse[T](BaseModel):
    """
    JAVA: public record ApiResponse<T>(boolean success, String message, T data)

    `class ApiResponse[T]` is the modern generic syntax (Python 3.12+). Older
    code writes `class ApiResponse(BaseModel, Generic[T])` with a separate
    `T = TypeVar("T")` line - you will see both in the wild.
    """

    success: bool = True
    message: str = "Success"
    data: T | None = None


class ErrorResponse(BaseModel):
    """Same shape, plus the bits you only need when something went wrong."""

    success: bool = False
    message: str
    data: None = None
    error: dict = Field(default_factory=dict)
    request_id: str | None = None


def ok(data=None, message: str = "Success") -> dict:
    """
    Build a success body.

    Returns a plain dict on purpose: FastAPI then validates it against the
    handler's `response_model=ApiResponse[Something]`, which is what converts
    a SQLAlchemy row into the right JSON and strips anything not in the model.
    """
    return {"success": True, "message": message, "data": data}
