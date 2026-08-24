"""
User business logic.

JAVA: @Service UserService, sitting between the controller and the repository.

Note there is no FastAPI import here. The HTTP layer catches these exceptions
and turns them into status codes; this file just knows about users. That split
is what lets the same function be called from a route AND from a CLI script.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models import RefreshToken, User

VALID_ROLES = ("user", "admin")


class UsernameAlreadyExists(Exception):
    """JAVA: a custom RuntimeException the @ControllerAdvice maps to 409."""


def normalize_username(username: str) -> str:
    """
    Lowercase and trim. Applied on BOTH write and lookup.

    Do this in exactly one place. If registration lowercases but login does
    not, "Admin" registers fine and then can never log in - a bug that only
    shows up for users who capitalise, which is most of them.
    """
    return username.strip().lower()


def get_by_username(db: Session, username: str) -> User | None:
    return db.execute(
        select(User).where(User.username == normalize_username(username))
    ).scalar_one_or_none()


def create_user(db: Session, username: str, password: str, role: str = "user") -> User:
    if role not in VALID_ROLES:
        raise ValueError(f"role must be one of {VALID_ROLES}")

    username = normalize_username(username)

    if get_by_username(db, username):
        raise UsernameAlreadyExists(username)

    user = User(username=username, hashed_password=hash_password(password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def ensure_admin(db: Session, username: str, password: str) -> tuple[User, bool]:
    """
    Idempotent admin bootstrap. Returns (user, created).

    Safe to run twice - on a second run it promotes the existing account rather
    than failing, and it does NOT touch the password. A seeding script that
    silently resets a password every deploy is a way to lock yourself out (or
    to hand the account back to whoever knew the old seed value).
    """
    user = get_by_username(db, username)

    if user is None:
        return create_user(db, username, password, role="admin"), True

    changed = False
    if user.role != "admin":
        user.role = "admin"
        changed = True
    if not user.is_active:
        user.is_active = True
        changed = True

    if changed:
        db.commit()
        db.refresh(user)

    return user, False


def set_password(db: Session, user: User, new_password: str) -> int:
    """
    Replace a password and kill every existing session. Returns how many
    sessions were revoked.

    The revocation is not optional. If a password change left refresh tokens
    alive, then resetting the password of a stolen account would achieve
    nothing - the attacker keeps refreshing their way back in. "Change password"
    and "log out everywhere" must be the same operation.
    """
    user.hashed_password = hash_password(new_password)

    revoked = (
        db.query(RefreshToken)
        .filter(RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False))
        .update({"revoked": True})
    )

    db.commit()
    db.refresh(user)
    return revoked
