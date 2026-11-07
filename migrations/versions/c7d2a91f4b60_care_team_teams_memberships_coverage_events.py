"""care_team teams, memberships, coverage and events

Revision ID: c7d2a91f4b60
Revises: a23046d4711b
Create Date: 2026-11-05 19:00:00

No foreign keys to directory's tables: client, provider and org ids are stored as
plain values, so the two contexts stay separable. The only cross-schema reference is
to identity.person, the one id every context shares. Periods are half-open
tstzrange, like the domain's TimeRange; exclusion constraints (btree_gist, created by
the directory migration) forbid overlaps the domain could miss under concurrency.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7d2a91f4b60"
down_revision: Union[str, Sequence[str], None] = "a23046d4711b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TIMESTAMPTZ = sa.DateTime(timezone=True)
DISCIPLINES = "'TRAINER', 'PHYSIO', 'PHYSICIAN', 'MASSAGE', 'NUTRITION'"
ENGAGEMENTS = "'ACTIVE', 'CONSULTING', 'ALUMNI'"
EVENT_TYPES = (
    "'MEMBER_ADDED', 'ENGAGEMENT_CHANGED', 'MEMBERSHIP_ENDED', 'COVERAGE_SCHEDULED',"
    " 'COVERAGE_ENDED', 'COVERAGE_CANCELLED', 'ORGANIZATION_DISCHARGED'"
)


def upgrade() -> None:
    op.create_table(
        "care_team",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("client_id", sa.Uuid, nullable=False, unique=True),  # one team per client
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),  # optimistic locking
        schema="care_team",
    )

    op.create_table(
        "membership",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("team_id", sa.Uuid, sa.ForeignKey("care_team.care_team.id"), nullable=False),
        sa.Column("provider_id", sa.Uuid, nullable=False),
        sa.Column("discipline", sa.Text, nullable=False),
        sa.Column("org_context_id", sa.Uuid),  # NULL: a solo provider
        sa.Column("engagement", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("valid_from", TIMESTAMPTZ, nullable=False),
        sa.Column("valid_to", TIMESTAMPTZ),  # NULL: still running
        sa.CheckConstraint(f"discipline IN ({DISCIPLINES})", name="known_discipline"),
        sa.CheckConstraint(f"engagement IN ({ENGAGEMENTS})", name="known_engagement"),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="period_moves_forward"),
        schema="care_team",
    )
    # A provider never has two overlapping memberships on the same team.
    op.execute(
        """
        ALTER TABLE care_team.membership
        ADD CONSTRAINT one_membership_per_provider_at_a_time
        EXCLUDE USING gist (team_id WITH =, provider_id WITH =, tstzrange(valid_from, valid_to) WITH &&)
        """
    )

    op.create_table(
        "coverage",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("covered_membership_id", sa.Uuid, sa.ForeignKey("care_team.membership.id"), nullable=False),
        sa.Column("covering_provider_id", sa.Uuid, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("valid_from", TIMESTAMPTZ, nullable=False),
        sa.Column("valid_to", TIMESTAMPTZ, nullable=False),  # a coverage always has an end
        sa.Column("cancelled_at", TIMESTAMPTZ),
        sa.CheckConstraint("valid_to > valid_from", name="window_moves_forward"),
        schema="care_team",
    )
    # One live coverage per membership at any instant; a cancelled one frees its window.
    op.execute(
        """
        ALTER TABLE care_team.coverage
        ADD CONSTRAINT one_live_coverage_at_a_time
        EXCLUDE USING gist (covered_membership_id WITH =, tstzrange(valid_from, valid_to) WITH &&)
        WHERE (cancelled_at IS NULL)
        """
    )

    op.create_table(
        "team_event",
        sa.Column("seq", sa.BigInteger, sa.Identity(always=True), primary_key=True),  # the order events happened in
        sa.Column("id", sa.Uuid, nullable=False, unique=True),
        sa.Column("team_id", sa.Uuid, sa.ForeignKey("care_team.care_team.id"), nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("actor_id", sa.Uuid, sa.ForeignKey("identity.person.id"), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("at", TIMESTAMPTZ, nullable=False),
        sa.Column("subject_id", sa.Uuid, nullable=False),  # a membership, coverage or org
        sa.CheckConstraint(f"type IN ({EVENT_TYPES})", name="known_event_type"),
        schema="care_team",
    )


def downgrade() -> None:
    op.drop_table("team_event", schema="care_team")
    op.drop_table("coverage", schema="care_team")
    op.drop_table("membership", schema="care_team")
    op.drop_table("care_team", schema="care_team")
