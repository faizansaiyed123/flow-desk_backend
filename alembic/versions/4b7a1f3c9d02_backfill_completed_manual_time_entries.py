"""backfill manual duration entries that were mistaken for running timers

Revision ID: 4b7a1f3c9d02
Revises: aef478de41c6
Create Date: 2026-10-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4b7a1f3c9d02"
down_revision: Union[str, None] = "aef478de41c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Before the service fix, manually logged rows with duration_minutes but no
    # ended_at were persisted as if a timer were still running. Convert only
    # valid positive-duration rows; an actual running timer has no duration.
    op.execute(
        sa.text(
            """
            UPDATE time_entries
            SET ended_at = started_at + (duration_minutes * INTERVAL '1 minute')
            WHERE ended_at IS NULL
              AND duration_minutes IS NOT NULL
              AND duration_minutes > 0
            """
        )
    )


def downgrade() -> None:
    # This is a corrective data migration. Reverting it would make historical
    # completed manual entries look like active timers again, and there is no
    # safe way to distinguish rows repaired here from other completed entries.
    pass
