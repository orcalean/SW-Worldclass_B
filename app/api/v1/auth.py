"""Login endpoints (ADR 0009). Not behind `require_auth`; everything else under /v1 is.

  POST /v1/auth/login   {email, password} -> sets HttpOnly session cookie, returns the user
  POST /v1/auth/logout  ends the session, clears the cookie
  GET  /v1/auth/me      {user | null, auth_required}; the UI calls it on load (cookie survives refresh)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app import auth
from app.config import get_settings
from app.storage import db

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str | None = None


class SessionOut(BaseModel):
    user: UserOut | None = None
    auth_required: bool


def _out(u: db.User) -> UserOut:
    return UserOut(id=u.id, email=u.email, name=u.name)


@router.post("/login")
def login(body: LoginIn, response: Response) -> UserOut:
    user = auth.authenticate(body.email, body.password)
    if user is None:
        raise HTTPException(401, "invalid email or password")
    s = get_settings()
    response.set_cookie(auth.COOKIE, auth.create_session(user), max_age=s.session_days * 86400,
                        httponly=True, samesite="lax", secure=s.cookie_secure, path="/")
    return _out(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    auth.delete_session(request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE, path="/")


@router.get("/me")
def me(request: Request) -> SessionOut:
    user = auth.user_for_token(request.cookies.get(auth.COOKIE))
    return SessionOut(user=_out(user) if user else None, auth_required=auth.login_required())
