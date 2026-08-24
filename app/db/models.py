"""
Database tables.

JAVA: @Entity classes. SQLAlchemy 2.0's Mapped[] syntax is very close to JPA,
      and gives you real type checking on top.
"""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Stored lowercase - see user_service.normalize_username. Without that,
    # "Admin" and "admin" become two different accounts, and users cannot log
    # in because they capitalised differently than at signup.
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)

    # NEVER a `password` column. Only ever the hash.
    hashed_password: Mapped[str] = mapped_column(String(255))

    role: Mapped[str] = mapped_column(String(20), default="user")   # user | admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(Base):
    """
    Storing refresh tokens is what makes logout actually work.

    A JWT access token cannot be revoked - it is valid until it expires.
    So: access tokens live 15 minutes, and the long-lived credential is a
    refresh token row you can delete. Logout = delete the row.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")

    def is_usable(self) -> bool:
        expires = self.expires_at
        if expires.tzinfo is None:          # SQLite loses the timezone
            expires = expires.replace(tzinfo=UTC)
        return not self.revoked and expires > utcnow()


class Document(Base):
    """
    One uploaded file, owned by one user.

    Multi-tenancy lives in this `user_id` column. Every query that touches
    documents or chunks MUST filter on it - otherwise one customer's questions
    get answered from another customer's data, which is the worst bug this
    kind of product can have.
    """

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # What the user called it - shown back to them, never used as a path.
    filename: Mapped[str] = mapped_column(String(255))

    # Where we actually put it: a generated UUID name, so a malicious filename
    # cannot escape the storage directory.
    stored_path: Mapped[str] = mapped_column(String(500))

    size_bytes: Mapped[int] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    """
    A searchable slice of a document.

    Chunking exists because retrieval works better on paragraphs than on whole
    files: a 50-page manual matches almost every query weakly, while the right
    paragraph matches one query strongly.
    """

    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    # Denormalised on purpose: lets the search query filter by user without
    # joining through documents on every request.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    position: Mapped[int] = mapped_column(Integer)      # order within the file
    content: Mapped[str] = mapped_column(Text)

    document: Mapped["Document"] = relationship(back_populates="chunks")


class ApiKey(Base):
    """For server-to-server callers that cannot run a login flow."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    name: Mapped[str] = mapped_column(String(100))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
