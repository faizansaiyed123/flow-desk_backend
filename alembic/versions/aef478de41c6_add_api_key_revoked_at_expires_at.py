"""add api_key revoked_at expires_at

Revision ID: aef478de41c6
Revises: 8f88364e278d
Create Date: 2026-10-11 11:08:40.888876

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aef478de41c6'
down_revision: Union[str, None] = '8f88364e278d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('api_keys', sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('api_keys', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_api_keys_revoked_at'), 'api_keys', ['revoked_at'], unique=False)
    op.create_index(op.f('ix_api_keys_expires_at'), 'api_keys', ['expires_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_api_keys_expires_at'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_revoked_at'), table_name='api_keys')
    op.drop_column('api_keys', 'expires_at')
    op.drop_column('api_keys', 'revoked_at')
