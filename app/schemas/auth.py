"""
Auth DTOs.

JAVA: request/response records + Bean Validation annotations.

The important pattern here: UserOut has NO password field. The response model
is a different class from the entity, so you physically cannot leak the hash.
"""

import re
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

# JAVA: @Pattern(regexp="^[a-zA-Z0-9._-]+$") @Size(min=3, max=50)
#
# Letters, digits, dot, underscore, hyphen. No spaces, no @, no unicode.
# Being strict here is a security choice, not a style one: unicode lookalikes
# let someone register "аdmin" (Cyrillic а) and impersonate "admin".
Username = Annotated[
    str,
    StringConstraints(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9._-]+$"),
]


class UserCreate(BaseModel):
    username: Username
    password: str = Field(min_length=12, max_length=72)

    @field_validator("password")
    @classmethod
    def _strong_enough(cls, v: str) -> str:
        # bcrypt ignores anything past 72 bytes; reject rather than silently cut
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password too long (max 72 bytes)")
        if not re.search(r"[a-z]", v) or not re.search(r"[A-Z]", v):
            raise ValueError("Password needs upper and lower case letters")
        if not re.search(r"\d", v):
            raise ValueError("Password needs at least one digit")
        return v


class LoginRequest(BaseModel):
    """
    Plain JSON login - no OAuth2 form, no client_id/client_secret.

    JAVA: @RequestBody LoginRequest, exactly what you are used to.

    Note the loose rules here. `username` is a plain str, not the strict
    `Username` type, and the password has no strength check:
      - a 422 for "bad username format" would tell an attacker which strings
        are even possible accounts, and
      - format rules can change over time; an existing user whose credential
        predates a rule must still be able to log in.
    Validation strictness belongs at REGISTRATION. Login just checks the hash.
    """

    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=72)


class UserOut(BaseModel):
    # from_attributes lets Pydantic read a SQLAlchemy object directly.
    # JAVA: a MapStruct mapper, but free.
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int                       # seconds - so the client can pre-refresh


class RefreshRequest(BaseModel):
    refresh_token: str


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ApiKeyOut(BaseModel):
    id: int
    name: str
    key: str = Field(description="Shown ONCE. It is not recoverable.")
