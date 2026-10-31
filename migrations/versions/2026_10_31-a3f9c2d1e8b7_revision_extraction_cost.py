"""revision extraction cost

Revision ID: a3f9c2d1e8b7
Revises: 7c41e2a9b3d5
Create Date: 2026-10-31 12:00:00.000000

"""
import hashlib
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a3f9c2d1e8b7'
down_revision: Union[str, Sequence[str], None] = '7c41e2a9b3d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen copy of how services.ingest_bytes keyed the extraction cache when this migration was written.
_KEY_VARIANTS = [("extract-1.0", "anthropic", "claude-sonnet-5-5"), ("extract-1.0", "offline", "offline")]


def upgrade() -> None:
    """Revisions record what extracting them cost. Old revisions are backfilled from the extraction cache
    (which kept the first-run cost); anything not found stays NULL (= not recorded)."""
    with op.batch_alter_table('revisions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('extraction_cost_usd', sa.Float(), nullable=True))

    conn = op.get_bind()
    costs = dict(conn.execute(sa.text("SELECT key, cost_usd FROM extraction_cache")).all())
    seen: set[str] = set()  # a file re-uploaded hit the cache: only its first revision paid
    rows = conn.execute(sa.text(
        "SELECT id, sha256 FROM revisions WHERE sha256 IS NOT NULL ORDER BY created_at")).all()
    for rev_id, sha in rows:
        for prompt, llm, model in _KEY_VARIANTS:
            key = hashlib.sha256(f"{sha}|{prompt}|{llm}|{model}".encode()).hexdigest()
            if key in costs:
                cost = 0.0 if key in seen else float(costs[key] or 0.0)
                seen.add(key)
                conn.execute(sa.text("UPDATE revisions SET extraction_cost_usd = :c WHERE id = :i"),
                             {"c": cost, "i": rev_id})
                break


def downgrade() -> None:
    with op.batch_alter_table('revisions', schema=None) as batch_op:
        batch_op.drop_column('extraction_cost_usd')
