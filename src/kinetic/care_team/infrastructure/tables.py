"""How the care team is stored: SQLAlchemy table models in the `care_team` schema.

Must match the hand-written migration. actor_id references identity.person in the
database, but that foreign key is left out here so this metadata never needs
identity's table models.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Identity, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class CareTeamBase(DeclarativeBase):
    metadata = MetaData(schema="care_team")
    type_annotation_map = {datetime: DateTime(timezone=True)}


class CareTeamRow(CareTeamBase):
    __tablename__ = "care_team"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    client_id: Mapped[UUID] = mapped_column(unique=True)
    version: Mapped[int]


class MembershipRow(CareTeamBase):
    __tablename__ = "membership"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("care_team.care_team.id"))
    provider_id: Mapped[UUID]
    discipline: Mapped[str]
    org_context_id: Mapped[UUID | None]
    engagement: Mapped[str]
    reason: Mapped[str]
    valid_from: Mapped[datetime]
    valid_to: Mapped[datetime | None]


class CoverageRow(CareTeamBase):
    __tablename__ = "coverage"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    covered_membership_id: Mapped[UUID] = mapped_column(ForeignKey("care_team.membership.id"))
    covering_provider_id: Mapped[UUID]
    reason: Mapped[str]
    valid_from: Mapped[datetime]
    valid_to: Mapped[datetime]
    cancelled_at: Mapped[datetime | None]


class TeamEventRow(CareTeamBase):
    __tablename__ = "team_event"

    seq: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    id: Mapped[UUID] = mapped_column(unique=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("care_team.care_team.id"))
    type: Mapped[str]
    actor_id: Mapped[UUID]
    reason: Mapped[str]
    at: Mapped[datetime]
    subject_id: Mapped[UUID]


class CareInvitationRow(CareTeamBase):
    __tablename__ = "care_invitation"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    provider_id: Mapped[UUID]
    client_email: Mapped[str]
    discipline: Mapped[str]
    reason: Mapped[str]
    token_hash: Mapped[str] = mapped_column(unique=True)
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    accepted_at: Mapped[datetime | None]
    accepted_by: Mapped[UUID | None]
