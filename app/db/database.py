"""
Database engine + session.

JAVA: DataSource + EntityManagerFactory + @Transactional session handling.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# SQLite needs one extra flag because FastAPI serves requests on many threads.
# Postgres does not - hence the conditional.
connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,      # drop dead connections instead of erroring. ALWAYS on.
    echo=settings.debug,     # logs every SQL statement (like show-sql: true)
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """JAVA: nothing - it is the base every @Entity inherits from."""


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency: opens a session, hands it to the handler, and ALWAYS
    closes it - even if the handler raises.

    JAVA: this is what @Transactional does for you invisibly. Here it is
          explicit, which is easier to debug and easier to get wrong.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
