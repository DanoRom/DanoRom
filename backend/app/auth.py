"""Session-based auth helpers.

Uses only the standard library for cryptography (hashlib.pbkdf2_hmac +
secrets) so the platform never needs a new pip dependency, per CLAUDE.md's
free/permissive-only rule.
"""

import hashlib
import hmac
import secrets

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .models import Project
from .models import Session as SessionModel
from .models import User

PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, hash_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return hmac.compare_digest(digest.hex(), hash_hex)


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


def _resolve_token(authorization: str | None, db: Session) -> User | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[len("Bearer ") :].strip()
    if not token:
        return None
    session = db.query(SessionModel).filter(SessionModel.token == token).first()
    if session is None:
        return None
    return db.get(User, session.user_id)


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    user = _resolve_token(authorization, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def get_current_user_optional(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User | None:
    return _resolve_token(authorization, db)


def ensure_project_access(project: Project, user: User | None) -> None:
    """Legacy (owner_id IS NULL) projects stay open to everyone; owned
    projects are only writable by their owner."""
    if project.owner_id is not None and (user is None or project.owner_id != user.id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
