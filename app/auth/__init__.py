"""User login (ADR 0009): scrypt password hashes, DB-backed sessions in an HttpOnly cookie.

A /v1 request is allowed with a valid session cookie OR a valid X-API-Key (service callers such as SWP)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Header, HTTPException, Request
from sqlalchemy import delete, select

from app.config import get_settings
from app.storage import db

COOKIE = "swc_session"
_N, _R, _P = 2**14, 8, 1  # scrypt cost (~16 MB, ~50 ms)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    salt64, dk64 = base64.b64encode(salt).decode(), base64.b64encode(dk).decode()
    return f"scrypt${_N}${_R}${_P}${salt64}${dk64}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        expected = base64.b64decode(dk)
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                             dklen=len(expected))
    except ValueError:
        return False
    return hmac.compare_digest(got, expected)


# Checked when the email is unknown, so response time doesn't reveal which emails exist.
_DUMMY_HASH = hash_password(secrets.token_hex(8))


def _token_id(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # SQLite drops tzinfo


def authenticate(email: str, password: str) -> db.User | None:
    with db.session() as ses:
        user = ses.scalar(select(db.User).where(db.User.email == normalize_email(email)))
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, user.password_hash) or not user.is_active:
        return None
    return user


def create_session(user: db.User) -> str:
    """New session for `user`; returns the cookie token. Also drops the user's expired sessions."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    with db.session() as ses:
        ses.execute(delete(db.UserSession).where(db.UserSession.user_id == user.id,
                                                 db.UserSession.expires_at < now))
        ses.add(db.UserSession(id=_token_id(token), user_id=user.id,
                               expires_at=now + timedelta(days=get_settings().session_days)))
        ses.commit()
    return token


def user_for_token(token: str | None) -> db.User | None:
    if not token:
        return None
    with db.session() as ses:
        s = ses.get(db.UserSession, _token_id(token))
        if s is None or _aware(s.expires_at) <= datetime.now(timezone.utc) or not s.user.is_active:
            return None
        return s.user


def delete_session(token: str | None) -> None:
    if not token:
        return
    with db.session() as ses:
        ses.execute(delete(db.UserSession).where(db.UserSession.id == _token_id(token)))
        ses.commit()


def _api_keys() -> set[str]:
    return {k.strip() for k in get_settings().api_keys.split(",") if k.strip()}


def login_required() -> bool:
    """Whether the UI must show the login page (auth on, or API keys set so anonymous calls fail)."""
    return get_settings().auth_required or bool(_api_keys())


def require_auth(request: Request, x_api_key: Annotated[str | None, Header()] = None) -> None:
    """Router dependency for every /v1 route except /v1/auth/*."""
    keys = _api_keys()
    if x_api_key and x_api_key in keys:
        return
    if user_for_token(request.cookies.get(COOKIE)):
        return
    if not login_required():
        return
    raise HTTPException(401, "not signed in (session cookie or X-API-Key required)")
