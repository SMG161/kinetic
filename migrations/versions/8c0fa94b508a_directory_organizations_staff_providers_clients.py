"""directory organizations, staff, providers and clients

Revision ID: 8c0fa94b508a
Revises: 123a6507dfbc
Create Date: 2026-11-04 10:00:00

The value lists below are copied, not imported from the domain: a migration must
keep meaning what it meant when it ran, even after the code changes.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "8c0fa94b508a"
down_revision: Union[str, Sequence[str], None] = "123a6507dfbc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TIMESTAMPTZ = sa.DateTime(timezone=True)
DISCIPLINES = "ARRAY['TRAINER', 'PHYSIO', 'PHYSICIAN', 'MASSAGE', 'NUTRITION']::text[]"
PERSON_FK = "identity.person.id"


def upgrade() -> None:
    op.create_table(
        "organization",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False),
        schema="directory",
    )
    op.create_table(
        "staff_membership",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("organization_id", sa.Uuid, sa.ForeignKey("directory.organization.id"), nullable=False),
        sa.Column("person_id", sa.Uuid, sa.ForeignKey(PERSON_FK), nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("disciplines", ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False),
        sa.UniqueConstraint("organization_id", "person_id", "role"),
        sa.CheckConstraint("role IN ('OWNER', 'ADMIN', 'FRONT_DESK', 'PRACTITIONER')", name="valid_role"),
        sa.CheckConstraint(f"disciplines <@ {DISCIPLINES}", name="valid_disciplines"),
        # Practitioners practise at least one discipline; nobody else has any.
        sa.CheckConstraint("(role = 'PRACTITIONER') = (cardinality(disciplines) > 0)", name="disciplines_iff_practitioner"),
        schema="directory",
    )
    # Exactly one owner per org.
    op.create_index(
        "one_owner_per_organization",
        "staff_membership",
        ["organization_id"],
        unique=True,
        schema="directory",
        postgresql_where=sa.text("role = 'OWNER'"),
    )
    op.create_table(
        "provider",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("person_id", sa.Uuid, sa.ForeignKey(PERSON_FK), nullable=False, unique=True),
        sa.Column("qualifications", ARRAY(sa.Text), nullable=False),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False),
        sa.CheckConstraint(f"qualifications <@ {DISCIPLINES}", name="valid_qualifications"),
        sa.CheckConstraint("cardinality(qualifications) > 0", name="at_least_one_qualification"),
        schema="directory",
    )
    op.create_table(
        "client",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("person_id", sa.Uuid, sa.ForeignKey(PERSON_FK), nullable=False, unique=True),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False),
        schema="directory",
    )


def downgrade() -> None:
    op.drop_table("client", schema="directory")
    op.drop_table("provider", schema="directory")
    op.drop_index("one_owner_per_organization", table_name="staff_membership", schema="directory")
    op.drop_table("staff_membership", schema="directory")
    op.drop_table("organization", schema="directory")
