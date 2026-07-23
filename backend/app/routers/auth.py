import re

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import create_session_token, get_current_user, hash_password, verify_password
from ..database import get_db
from ..models import Session as SessionModel
from ..models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,30}$")


class AuthCredentials(BaseModel):
    username: str
    password: str


class AuthOut(BaseModel):
    token: str
    username: str


class MeOut(BaseModel):
    username: str


@router.post("/register", response_model=AuthOut, status_code=201)
def register(payload: AuthCredentials, db: Session = Depends(get_db)):
    username = payload.username.strip()
    if not USERNAME_RE.match(username):
        raise HTTPException(
            status_code=422,
            detail="Username must be 3-30 characters: letters, numbers, - or _",
        )
    if len(payload.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")
    if db.query(User).filter(User.username == username).first() is not None:
        raise HTTPException(status_code=409, detail="Username is already taken")

    user = User(username=username, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_session_token()
    db.add(SessionModel(token=token, user_id=user.id))
    db.commit()
    return AuthOut(token=token, username=user.username)


@router.post("/login", response_model=AuthOut)
def login(payload: AuthCredentials, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username.strip()).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_session_token()
    db.add(SessionModel(token=token, user_id=user.id))
    db.commit()
    return AuthOut(token=token, username=user.username)


@router.post("/logout", status_code=204)
def logout(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer ") :].strip()
        if token:
            db.query(SessionModel).filter(SessionModel.token == token).delete()
            db.commit()


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    return MeOut(username=user.username)
