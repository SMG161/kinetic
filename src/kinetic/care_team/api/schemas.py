"""HTTP shapes for the care team. Enums validate disciplines and engagements; times must carry a zone."""

from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel

from kinetic.care_team.application.services import TeamHistory, TeamSnapshot
from kinetic.care_team.domain.facts import Discipline
from kinetic.care_team.domain.model import Coverage, Engagement, Membership, TeamEvent, TeamEventType


class AddMemberRequest(BaseModel):
    provider_email: str
    discipline: Discipline
    org_id: UUID | None = None  # None: a solo provider (refused until care invitations exist)
    engagement: Engagement = Engagement.ACTIVE
    reason: str


class ChangeEngagementRequest(BaseModel):
    engagement: Engagement
    reason: str


class ReasonRequest(BaseModel):
    reason: str


class ScheduleCoverageRequest(BaseModel):
    covering_provider_email: str
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    reason: str


class MembershipResponse(BaseModel):
    id: UUID
    provider_id: UUID
    discipline: Discipline
    org_context_id: UUID | None
    engagement: Engagement
    reason: str
    valid_from: datetime
    valid_to: datetime | None

    @classmethod
    def of(cls, m: Membership) -> "MembershipResponse":
        return cls(
            id=m.id, provider_id=m.provider_id, discipline=m.discipline, org_context_id=m.org_context,
            engagement=m.engagement, reason=m.reason, valid_from=m.period.start, valid_to=m.period.end,
        )


class CoverageResponse(BaseModel):
    id: UUID
    covered_membership_id: UUID
    covering_provider_id: UUID
    reason: str
    starts_at: datetime
    ends_at: datetime | None
    cancelled_at: datetime | None

    @classmethod
    def of(cls, c: Coverage) -> "CoverageResponse":
        return cls(
            id=c.id, covered_membership_id=c.covered_membership_id, covering_provider_id=c.covering_provider_id,
            reason=c.reason, starts_at=c.window.start, ends_at=c.window.end, cancelled_at=c.cancelled_at,
        )


class PracticeLeadResponse(BaseModel):
    organization_id: UUID
    person_id: UUID


class TeamResponse(BaseModel):
    client_id: UUID
    at: datetime
    members: list[MembershipResponse]
    coverages: list[CoverageResponse]
    practice_leads: list[PracticeLeadResponse]

    @classmethod
    def of(cls, s: TeamSnapshot) -> "TeamResponse":
        return cls(
            client_id=s.client_id,
            at=s.at,
            members=[MembershipResponse.of(m) for m in s.memberships],
            coverages=[CoverageResponse.of(c) for c in s.coverages],
            practice_leads=[PracticeLeadResponse(organization_id=o, person_id=p) for o, p in s.practice_leads.items()],
        )


class TeamEventResponse(BaseModel):
    type: TeamEventType
    actor_id: UUID
    reason: str
    at: datetime
    subject_id: UUID

    @classmethod
    def of(cls, e: TeamEvent) -> "TeamEventResponse":
        return cls(type=e.type, actor_id=e.actor, reason=e.reason, at=e.at, subject_id=e.subject_id)


class HistoryResponse(BaseModel):
    """Every period ever recorded, closed ones included, and every event in order."""

    memberships: list[MembershipResponse]
    coverages: list[CoverageResponse]
    events: list[TeamEventResponse]

    @classmethod
    def of(cls, h: TeamHistory) -> "HistoryResponse":
        return cls(
            memberships=[MembershipResponse.of(m) for m in h.memberships],
            coverages=[CoverageResponse.of(c) for c in h.coverages],
            events=[TeamEventResponse.of(e) for e in h.events],
        )
