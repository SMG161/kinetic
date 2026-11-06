"""directory client relationships and practice leads

Revision ID: 5ebab937b2cf
Revises: 8c0fa94b508a
Create Date: 2026-11-04 14:00:00

Periods are stored as valid_from / valid_to (NULL = still running) and compared as
tstzrange, which is half-open [from, to) like the domain's TimeRange. Exclusion
constraints forbid overlapping periods; btree_gist lets them compare ids with "=".
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5ebab937b2cf"
down_revision: Union[str, Sequence[str], None] = "8c0fa94b508a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TIMESTAMPTZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "client_relationship",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("organization_id", sa.Uuid, sa.ForeignKey("directory.organization.id"), nullable=False),
        sa.Column("client_id", sa.Uuid, sa.ForeignKey("directory.client.id"), nullable=False),
        sa.Column("valid_from", TIMESTAMPTZ, nullable=False),
        sa.Column("valid_to", TIMESTAMPTZ),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="period_moves_forward"),
        schema="directory",
    )
    # An org serves a client through at most one relationship at any instant.
    op.execute(
        """
        ALTER TABLE directory.client_relationship
        ADD CONSTRAINT one_relationship_at_a_time
        EXCLUDE USING gist (organization_id WITH =, client_id WITH =, tstzrange(valid_from, valid_to) WITH &&)
        """
    )

    op.create_table(
        "practice_lead_assignment",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("relationship_id", sa.Uuid, sa.ForeignKey("directory.client_relationship.id"), nullable=False),
        sa.Column("person_id", sa.Uuid, sa.ForeignKey("identity.person.id"), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("valid_from", TIMESTAMPTZ, nullable=False),
        sa.Column("valid_to", TIMESTAMPTZ),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="period_moves_forward"),
        schema="directory",
    )
    # At most one practice lead per relationship at any instant. Two admins handing
    # off at the same moment would both pass the domain check; this stops the second.
    op.execute(
        """
        ALTER TABLE directory.practice_lead_assignment
        ADD CONSTRAINT one_lead_at_a_time
        EXCLUDE USING gist (relationship_id WITH =, tstzrange(valid_from, valid_to) WITH &&)
        """
    )


def downgrade() -> None:
    op.drop_table("practice_lead_assignment", schema="directory")
    op.drop_table("client_relationship", schema="directory")
    # btree_gist stays: care_team's constraints will rely on it too.
