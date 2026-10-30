"""Seed / manage login users (there is no sign-up page).

  uv run python -m app.auth.seed alice@plant.com --name "Alice"      # add or reset password (prompts)
  uv run python -m app.auth.seed alice@plant.com --password 's3cret'  # non-interactive
  uv run python -m app.auth.seed --file users.json                   # [{"email","name","password"}, ...]
  uv run python -m app.auth.seed --list
  uv run python -m app.auth.seed alice@plant.com --deactivate        # blocks login, ends their sessions
  uv run python -m app.auth.seed alice@plant.com --claim-orphans     # give SOPs with no uploader to this user

Uses the database from .env (DATABASE_URL / SWC_DATABASE_URL, else local SQLite)."""
from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from sqlalchemy import delete, select, update

from app.auth import hash_password, normalize_email
from app.storage import db

MIN_PASSWORD = 8


def upsert(email: str, password: str, name: str | None = None) -> str:
    """Create the user, or reset password (and name, if given) and reactivate. Returns 'created'/'updated'."""
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"{email}: password must be at least {MIN_PASSWORD} characters")
    email = normalize_email(email)
    with db.session() as ses:
        user = ses.scalar(select(db.User).where(db.User.email == email))
        if user is None:
            ses.add(db.User(email=email, name=name, password_hash=hash_password(password)))
            action = "created"
        else:
            user.password_hash = hash_password(password)
            user.is_active = True
            if name is not None:
                user.name = name
            ses.execute(delete(db.UserSession).where(db.UserSession.user_id == user.id))
            action = "updated"
        ses.commit()
    return action


def deactivate(email: str) -> bool:
    with db.session() as ses:
        user = ses.scalar(select(db.User).where(db.User.email == normalize_email(email)))
        if user is None:
            return False
        user.is_active = False
        ses.execute(delete(db.UserSession).where(db.UserSession.user_id == user.id))
        ses.commit()
    return True


def claim_orphans(email: str) -> int | None:
    """Make `email` the owner of every SOP without one (uploaded before ADR 0010 or via API key). None = no such user."""
    with db.session() as ses:
        user = ses.scalar(select(db.User).where(db.User.email == normalize_email(email)))
        if user is None:
            return None
        n = ses.execute(update(db.SOP).where(db.SOP.owner_id.is_(None)).values(owner_id=user.id)).rowcount
        ses.commit()
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.auth.seed", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("email", nargs="?")
    ap.add_argument("--name")
    ap.add_argument("--password", help="omit to be prompted (keeps it out of shell history)")
    ap.add_argument("--file", type=Path, help='JSON list of {"email", "name", "password"}')
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--deactivate", action="store_true")
    ap.add_argument("--claim-orphans", action="store_true", help="assign SOPs with no uploader to this user")
    a = ap.parse_args(argv)

    try:
        if a.list:
            with db.session() as ses:
                for u in ses.scalars(select(db.User).order_by(db.User.email)):
                    print(f"{u.email:40} {u.name or '':30} {'active' if u.is_active else 'INACTIVE'}")
        elif a.file:
            for u in json.loads(a.file.read_text()):
                print(f"{upsert(u['email'], u['password'], u.get('name'))}: {u['email']}")
        elif a.email and a.claim_orphans:
            n = claim_orphans(a.email)
            if n is None:
                print(f"no such user: {a.email}", file=sys.stderr)
                return 1
            print(f"{n} SOP(s) now owned by {a.email}")
        elif a.email and a.deactivate:
            if not deactivate(a.email):
                print(f"no such user: {a.email}", file=sys.stderr)
                return 1
            print(f"deactivated: {a.email}")
        elif a.email:
            password = a.password
            if password is None:
                password = getpass.getpass("Password: ")
                if password != getpass.getpass("Repeat: "):
                    print("passwords don't match", file=sys.stderr)
                    return 1
            print(f"{upsert(a.email, password, a.name)}: {a.email}")
        else:
            ap.print_help()
            return 1
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
