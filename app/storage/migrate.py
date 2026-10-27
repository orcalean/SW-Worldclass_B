"""Schema migrations (Alembic). The app upgrades the database to the latest revision when it first connects."""
from __future__ import annotations

import logging

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, pool

from app.config import BACKEND_DIR


def _config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["url"] = url
    cfg.attributes["configure_logging"] = False  # keep uvicorn's logging
    return cfg


def upgrade(url: str) -> None:
    """Bring the database to head. A database created by the old create_all() (tables, no alembic_version)
    is stamped as the initial revision first, so its existing data is kept."""
    logging.getLogger("alembic.runtime.plugins").setLevel(logging.WARNING)  # startup noise
    cfg = _config(url)
    engine = create_engine(url, poolclass=pool.NullPool)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    if "sops" in tables and "alembic_version" not in tables:
        command.stamp(cfg, "d461aa2027bc")
    command.upgrade(cfg, "head")
