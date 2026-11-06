"""directory invitations

Revision ID: a23046d4711b
Revises: 5ebab937b2cf
Create Date: 2026-11-04 18:00:00

One table for all three kinds. CHECK constraints make each kind carry exactly its
own fields, so a malformed invitation cannot be stored even by buggy code.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "a23046d4711b"
down_revision: Union[str, Sequence[str], None] = "5ebab937b2cf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TIMESTAMPTZ = sa.DateTime(timezone=True)
DISCIPLINES = "ARRAY['TRAINER', 'PHYSIO', 'PHYSICIAN', 'MASSAGE', 'NUTRITION']::text[]"
PERSON_FK = "identity.person.id"


def upgrade() -> None:
    op.create_table(
        "invitation",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("organization_id", sa.Uuid, sa.ForeignKey("directory.organization.id"), nullable=False),
        sa.Column("invited_by", sa.Uuid, sa.ForeignKey(PERSON_FK), nullable=False),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("role", sa.Text),
        sa.Column("disciplines", ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("practice_lead_id", sa.Uuid, sa.ForeignKey(PERSON_FK)),
        sa.Column("reason", sa.Text),
        sa.Column("token_hash", sa.Text, nullable=False, unique=True),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False),
        sa.Column("expires_at", TIMESTAMPTZ, nullable=False),
        sa.Column("accepted_at", TIMESTAMPTZ),
        sa.Column("accepted_by", sa.Uuid, sa.ForeignKey(PERSON_FK)),
        sa.CheckConstraint("kind IN ('STAFF', 'PRACTITIONER', 'CLIENT')", name="valid_kind"),
        sa.CheckConstraint(f"disciplines <@ {DISCIPLINES}", name="valid_disciplines"),
        sa.CheckConstraint(
            "kind <> 'STAFF' OR (role IN ('ADMIN', 'FRONT_DESK') AND cardinality(disciplines) = 0"
            " AND practice_lead_id IS NULL AND reason IS NULL)",
            name="staff_shape",
        ),
        sa.CheckConstraint(
            "kind <> 'PRACTITIONER' OR (role IS NULL AND cardinality(disciplines) > 0"
            " AND practice_lead_id IS NULL AND reason IS NULL)",
            name="practitioner_shape",
        ),
        sa.CheckConstraint(
            "kind <> 'CLIENT' OR (role IS NULL AND cardinality(disciplines) = 0"
            " AND practice_lead_id IS NOT NULL AND reason IS NOT NULL)",
            name="client_shape",
        ),
        sa.CheckConstraint("expires_at > created_at", name="expires_after_created"),
        sa.CheckConstraint("(accepted_at IS NULL) = (accepted_by IS NULL)", name="accepted_together"),
        schema="directory",
    )


def downgrade() -> None:
    op.drop_table("invitation", schema="directory")
