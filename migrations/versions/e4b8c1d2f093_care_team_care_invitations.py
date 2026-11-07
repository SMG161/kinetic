"""care_team care invitations

Revision ID: e4b8c1d2f093
Revises: c7d2a91f4b60
Create Date: 2026-11-05 22:00:00

A provider invites a client to add them to the client's care team as a solo member.
Only the token's hash is stored. provider_id is a plain value (no foreign key into
directory); accepted_by references identity.person, the one id every context shares.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4b8c1d2f093"
down_revision: Union[str, Sequence[str], None] = "c7d2a91f4b60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TIMESTAMPTZ = sa.DateTime(timezone=True)
DISCIPLINES = "'TRAINER', 'PHYSIO', 'PHYSICIAN', 'MASSAGE', 'NUTRITION'"


def upgrade() -> None:
    op.create_table(
        "care_invitation",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("provider_id", sa.Uuid, nullable=False),
        sa.Column("client_email", sa.Text, nullable=False),
        sa.Column("discipline", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("token_hash", sa.Text, nullable=False, unique=True),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False),
        sa.Column("expires_at", TIMESTAMPTZ, nullable=False),
        sa.Column("accepted_at", TIMESTAMPTZ),
        sa.Column("accepted_by", sa.Uuid, sa.ForeignKey("identity.person.id")),
        sa.CheckConstraint(f"discipline IN ({DISCIPLINES})", name="known_discipline"),
        sa.CheckConstraint("expires_at > created_at", name="expires_after_created"),
        sa.CheckConstraint("(accepted_at IS NULL) = (accepted_by IS NULL)", name="accepted_together"),
        schema="care_team",
    )


def downgrade() -> None:
    op.drop_table("care_invitation", schema="care_team")
