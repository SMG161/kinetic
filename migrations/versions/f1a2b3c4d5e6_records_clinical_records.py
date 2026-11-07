"""records clinical records

Revision ID: f1a2b3c4d5e6
Revises: e4b8c1d2f093
Create Date: 2026-11-05 23:30:00

Append-only notes about a client. client_id is a plain value (no foreign key into
directory); author_id references identity.person, the one id every context shares.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e4b8c1d2f093"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CATEGORIES = (
    "'MEDICAL_HISTORY', 'ASSESSMENT', 'ASSESSMENT_SUMMARY', 'CLINICAL_NOTE',"
    " 'SESSION_NOTE', 'TRAINING_PLAN', 'MASSAGE_PLAN', 'NUTRITION_PLAN'"
)


def upgrade() -> None:
    op.create_table(
        "clinical_record",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("client_id", sa.Uuid, nullable=False, index=True),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("author_id", sa.Uuid, sa.ForeignKey("identity.person.id"), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("written_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"category IN ({CATEGORIES})", name="known_category"),
        sa.CheckConstraint("length(body) BETWEEN 1 AND 5000", name="body_length"),
        schema="records",
    )


def downgrade() -> None:
    op.drop_table("clinical_record", schema="records")
