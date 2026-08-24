r"""
Create (or promote) the first admin user.

    # interactive - password is typed hidden, never in your shell history
    .\venv\Scripts\python.exe scripts\create_admin.py --username admin

    # non-interactive - generates a strong password and prints it ONCE
    .\venv\Scripts\python.exe scripts\create_admin.py --username admin --generate

    # CI / docker entrypoint (also read from .env)
    ADMIN_USERNAME=admin ADMIN_PASSWORD=... python scripts/create_admin.py

JAVA: a CommandLineRunner guarded by a profile, or a Flyway data migration.

Why a script and not a hardcoded seed row: a password committed to git is a
password owned by everyone who ever clones the repo. This way the secret exists
only in the operator's terminal.

Running it twice is safe - the second run promotes the existing account and
leaves the password alone.
"""

import argparse
import getpass
import secrets
import string
import sys
from pathlib import Path

# Make `import app...` work when this file is run directly as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.database import Base, SessionLocal, engine  # noqa: E402
from app.schemas.auth import UserCreate  # noqa: E402
from app.services.user_service import ensure_admin, set_password  # noqa: E402


def generate_password(length: int = 20) -> str:
    """
    Guarantees one of each required character class, then fills the rest
    randomly - otherwise a random string occasionally fails our own rules.
    """
    alphabet = string.ascii_letters + string.digits
    required = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
    ]
    rest = [secrets.choice(alphabet) for _ in range(length - len(required))]

    chars = required + rest
    secrets.SystemRandom().shuffle(chars)      # random.shuffle is NOT secure
    return "".join(chars)


def read_password(args) -> tuple[str, bool]:
    """Returns (password, was_generated)."""
    if args.generate:
        return generate_password(), True

    # get_settings() reads real env vars AND the .env file, so ADMIN_PASSWORD
    # works from either place. os.getenv alone would miss .env.
    from_config = get_settings().admin_password
    if from_config:
        return from_config, False

    if not sys.stdin.isatty():
        sys.exit(
            "No password available. Use --generate, or set ADMIN_PASSWORD, "
            "or run this in an interactive terminal."
        )

    first = getpass.getpass("Password: ")          # hidden input, no echo
    if first != getpass.getpass("Confirm password: "):
        sys.exit("Passwords do not match.")
    return first, False


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or promote an admin user")
    parser.add_argument("--username", default=get_settings().admin_username)
    parser.add_argument(
        "--generate",
        action="store_true",
        help="generate a strong password and print it once",
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="overwrite the password of an existing account (lost-password escape hatch)",
    )
    args = parser.parse_args()

    if not args.username:
        sys.exit("Missing --username (or set ADMIN_USERNAME).")

    password, generated = read_password(args)

    # Validate with the SAME rules as public registration. A seeded admin must
    # not be allowed a weaker password than a normal user.
    try:
        UserCreate(username=args.username, password=password)
    except ValidationError as e:
        for err in e.errors():
            print(f"  - {'.'.join(str(p) for p in err['loc'])}: {err['msg']}")
        sys.exit("Invalid username or password.")

    # The script may run before the app has ever started, so make sure the
    # tables exist. In production Alembic owns the schema and you would drop
    # this line.
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        user, created = ensure_admin(db, args.username, password)

        if created:
            print(f"\nAdmin created: {user.username} (id={user.id})")
            if generated:
                print(f"Password: {password}")
                print("^ Shown once. Store it in your password manager now.")

        elif args.reset_password:
            # Lost the password? This is the only way back in - there is no
            # way to read the old one, only to replace it.
            # set_password also revokes every active session.
            killed = set_password(db, user, password)

            print(f"\nPassword reset for: {user.username} (id={user.id})")
            print(f"Role is '{user.role}'. Revoked {killed} active session(s).")
            if generated:
                print(f"Password: {password}")
                print("^ Shown once. Store it in your password manager now.")

        else:
            print(f"\nUser already existed: {user.username} (id={user.id})")
            print(f"Role is now '{user.role}'. Password was left unchanged.")
            print("To set a new password, re-run with --reset-password")
            if generated:
                print("(The generated password was discarded - not needed.)")


if __name__ == "__main__":
    main()
