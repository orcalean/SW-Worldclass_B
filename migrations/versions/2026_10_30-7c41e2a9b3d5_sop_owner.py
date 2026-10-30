"""sop owner

Revision ID: 7c41e2a9b3d5
Revises: 19ee320bdd08
Create Date: 2026-10-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c41e2a9b3d5'
down_revision: Union[str, Sequence[str], None] = '19ee320bdd08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """SOPs get an uploader (users.id). Existing rows stay NULL until claimed: python -m app.auth.seed <email> --claim-orphans."""
    with op.batch_alter_table('sops', schema=None) as batch_op:
        batch_op.add_column(sa.Column('owner_id', sa.String(length=32), nullable=True))
        batch_op.create_index(batch_op.f('ix_sops_owner_id'), ['owner_id'], unique=False)
        batch_op.create_foreign_key('fk_sops_owner_id_users', 'users', ['owner_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('sops', schema=None) as batch_op:
        batch_op.drop_constraint('fk_sops_owner_id_users', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_sops_owner_id'))
        batch_op.drop_column('owner_id')
