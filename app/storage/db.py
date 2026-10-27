"""Persistence: SQLAlchemy (SQLite by default, Postgres via SWC_DATABASE_URL) + content-addressed blob dir."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from app.config import get_settings


def _id() -> str:
    return uuid.uuid4().hex[:16]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class SOP(Base):
    __tablename__ = "sops"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(300))
    plant: Mapped[str | None] = mapped_column(String(120))
    line: Mapped[str | None] = mapped_column(String(120))
    station: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    revisions: Mapped[list["Revision"]] = relationship(back_populates="sop", order_by="Revision.number")


class Revision(Base):
    __tablename__ = "revisions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    sop_id: Mapped[str] = mapped_column(ForeignKey("sops.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str | None] = mapped_column(String(300))
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="ingesting")  # ingesting|extracted|reviewed|failed
    document: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    sop: Mapped[SOP] = relationship(back_populates="revisions")
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="revision")
    assessments: Mapped[list["Assessment"]] = relationship(back_populates="revision",
                                                           order_by="Assessment.created_at")


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    revision_id: Mapped[str] = mapped_column(ForeignKey("revisions.id"), index=True)
    item: Mapped[dict] = mapped_column(JSON)  # EvidenceItem
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    revision: Mapped[Revision] = relationship(back_populates="evidence")


class Assessment(Base):
    __tablename__ = "assessments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    revision_id: Mapped[str | None] = mapped_column(ForeignKey("revisions.id"), index=True)
    cache_key: Mapped[str] = mapped_column(String(64), index=True)
    score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str | None] = mapped_column(String(40))
    result: Mapped[dict] = mapped_column(JSON)  # EvaluationResult
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    revision: Mapped[Revision | None] = relationship(back_populates="assessments")


class ExtractionCache(Base):
    __tablename__ = "extraction_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha(file + prompt version + model)
    document: Mapped[dict] = mapped_column(JSON)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|succeeded|failed
    stage: Mapped[str | None] = mapped_column(String(80))
    error: Mapped[str | None] = mapped_column(Text)
    result_type: Mapped[str | None] = mapped_column(String(40))
    result_id: Mapped[str | None] = mapped_column(String(32))
    result: Mapped[dict | None] = mapped_column(JSON)  # inline result for stateless black-box calls
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


@lru_cache
def _sessionmaker() -> sessionmaker[Session]:
    s = get_settings()
    url = s.database_url or f"sqlite:///{(s.data_dir / 'swc.db').resolve()}"
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def session() -> Session:
    return _sessionmaker()()


class Blobs:
    """Content-addressed files: <data_dir>/blobs/<sha>/<name>. URIs look like blob://<sha>/<name>."""

    def __init__(self, root: Path | None = None):
        self.root = (root or get_settings().data_dir) / "blobs"

    def put(self, sha: str, name: str, data: bytes) -> str:
        d = self.root / sha
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_bytes(data)
        return f"blob://{sha}/{name}"

    def path(self, sha: str, name: str) -> Path | None:
        p = (self.root / sha / name).resolve()
        if self.root.resolve() not in p.parents or not p.is_file():
            return None
        return p
