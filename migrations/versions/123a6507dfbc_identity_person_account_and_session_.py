"""identity person account and session tables

Revision ID: 123a6507dfbc
Revises: bc95080155ab
Create Date: 2026-11-03 19:22:20.267835

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '123a6507dfbc'
down_revision: Union[str, Sequence[str], None] = 'bc95080155ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TIMESTAMPTZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "person",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("full_name", sa.Text, nullable=False),
        sa.Column("email", sa.Text, nullable=False, unique=True),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False),
        schema="identity",
    )
    op.create_table(
        "account",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("person_id", sa.Uuid, sa.ForeignKey("identity.person.id"), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False),
        schema="identity",
    )
    op.create_table(
        "session",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("person_id", sa.Uuid, sa.ForeignKey("identity.person.id"), nullable=False),
        sa.Column("token_hash", sa.Text, nullable=False, unique=True),
        sa.Column("created_at", TIMESTAMPTZ, nullable=False),
        sa.Column("expires_at", TIMESTAMPTZ, nullable=False),
        sa.CheckConstraint("expires_at > created_at"),
        schema="identity",
    )


def downgrade() -> None:
    op.drop_table("session", schema="identity")
    op.drop_table("account", schema="identity")
    op.drop_table("person", schema="identity")
