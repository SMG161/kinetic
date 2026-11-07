"""The care team: the client's own team of providers, across every org that serves them.

Pure Python. Periods are never edited, only closed: a change closes one at t and opens
the next at t, so history is kept and there is no gap or overlap. Who may issue each
command is the AccessPolicy's decision, not this module's; the actor is recorded here.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from kinetic.care_team.domain.errors import (
    AlreadyOnTeam,
    InvalidCoverage,
    InvalidEngagement,
    InvalidOrgContext,
    InvalidReason,
    InvalidTiming,
    NotFound,
    NotQualified,
    SelfTreatment,
)
from kinetic.care_team.domain.facts import ClientFacts, Discipline, ProviderFacts
from kinetic.shared_kernel import ClientId, OrganizationId, PersonId, ProviderId, TimeRange

MAX_REASON_LENGTH = 500


class Engagement(StrEnum):
    ACTIVE = "ACTIVE"
    CONSULTING = "CONSULTING"
    ALUMNI = "ALUMNI"


class TeamEventType(StrEnum):
    MEMBER_ADDED = "MEMBER_ADDED"
    ENGAGEMENT_CHANGED = "ENGAGEMENT_CHANGED"
    MEMBERSHIP_ENDED = "MEMBERSHIP_ENDED"
    COVERAGE_SCHEDULED = "COVERAGE_SCHEDULED"
    COVERAGE_ENDED = "COVERAGE_ENDED"
    COVERAGE_CANCELLED = "COVERAGE_CANCELLED"
    ORGANIZATION_DISCHARGED = "ORGANIZATION_DISCHARGED"


@dataclass(frozen=True)
class Membership:
    """One provider, in one discipline, for one org (or solo), at one engagement, for one period."""

    id: UUID
    provider_id: ProviderId
    discipline: Discipline
    org_context: OrganizationId | None
    engagement: Engagement
    reason: str
    period: TimeRange


@dataclass(frozen=True)
class Coverage:
    """A colleague standing in for a membership during a window."""

    id: UUID
    covered_membership_id: UUID
    covering_provider_id: ProviderId
    window: TimeRange
    reason: str
    cancelled_at: datetime | None = None

    @property
    def is_live(self) -> bool:
        return self.cancelled_at is None

    def in_effect(self, at: datetime) -> bool:
        return self.is_live and self.window.contains(at)


@dataclass(frozen=True)
class TeamEvent:
    """Who did what to the team, when and why. subject_id is the membership, coverage or org."""

    type: TeamEventType
    actor: PersonId
    reason: str
    at: datetime
    subject_id: UUID


@dataclass
class CareTeam:
    """Aggregate root, one per client. Small enough to load whole."""

    id: UUID
    client_id: ClientId
    memberships: list[Membership]
    coverages: list[Coverage]
    events: list[TeamEvent]

    @classmethod
    def for_client(cls, client: ClientFacts) -> "CareTeam":
        return cls(id=uuid4(), client_id=client.client_id, memberships=[], coverages=[], events=[])

    def memberships_at(self, at: datetime) -> list[Membership]:
        """The team as it was at that instant."""
        return [m for m in self.memberships if m.period.contains(at)]

    # ---- Commands ----

    def add_member(
        self,
        actor: PersonId,
        provider: ProviderFacts,
        client: ClientFacts,
        discipline: Discipline,
        org_context: OrganizationId | None,
        engagement: Engagement,
        reason: str,
        at: datetime,
    ) -> Membership:
        self._require_own(client)
        reason = clean_reason(reason)
        if engagement is Engagement.ALUMNI:
            raise InvalidEngagement("a member joins as ACTIVE or CONSULTING")
        if provider.person_id == client.person_id:
            raise SelfTreatment("a client cannot be a member of their own care team")
        _check_org_context(provider, client, discipline, org_context)
        period = TimeRange(at)
        if any(m.provider_id == provider.provider_id and m.period.overlaps(period) for m in self.memberships):
            raise AlreadyOnTeam("this provider is already on the team")
        membership = Membership(uuid4(), provider.provider_id, discipline, org_context, engagement, reason, period)
        self.memberships.append(membership)
        self._record(TeamEventType.MEMBER_ADDED, actor, reason, at, membership.id)
        return membership

    def change_engagement(
        self, actor: PersonId, membership_id: UUID, engagement: Engagement, reason: str, at: datetime
    ) -> Membership:
        """Close the current period at t and open one with the new engagement at t."""
        current = self._open_membership(membership_id)
        if engagement is current.engagement:
            raise InvalidEngagement(f"the membership is already {engagement}")
        reason = clean_reason(reason)
        self._close(current, actor, reason, at)
        successor = replace(current, id=uuid4(), engagement=engagement, reason=reason, period=TimeRange(at))
        self.memberships.append(successor)
        self._record(TeamEventType.ENGAGEMENT_CHANGED, actor, reason, at, successor.id)
        return successor

    def end_membership(self, actor: PersonId, membership_id: UUID, reason: str, at: datetime) -> None:
        membership = self._open_membership(membership_id)
        reason = clean_reason(reason)
        self._close(membership, actor, reason, at)
        self._record(TeamEventType.MEMBERSHIP_ENDED, actor, reason, at, membership.id)

    def discharge_organization(self, actor: PersonId, org_id: OrganizationId, reason: str, at: datetime) -> None:
        """End every current membership in that org's context at the same instant."""
        reason = clean_reason(reason)
        leaving = [m for m in self.memberships if m.org_context == org_id and m.period.is_open]
        for membership in leaving:  # check all before changing any, so a failure changes nothing
            _require_after_start(membership, at)
        for membership in leaving:
            self._close(membership, actor, reason, at)
        self._record(TeamEventType.ORGANIZATION_DISCHARGED, actor, reason, at, org_id)

    def schedule_coverage(
        self,
        actor: PersonId,
        membership_id: UUID,
        covering: ProviderFacts,
        client: ClientFacts,
        window: TimeRange,
        reason: str,
        at: datetime,
    ) -> Coverage:
        self._require_own(client)
        covered = self._open_membership(membership_id)
        reason = clean_reason(reason)
        if window.end is None:
            raise InvalidCoverage("a coverage needs an end")
        if window.start < at:
            raise InvalidTiming("a coverage cannot start in the past")
        if not covered.period.encloses(window):
            raise InvalidCoverage("a coverage must fall inside the covered membership")
        if covering.provider_id == covered.provider_id:
            raise InvalidCoverage("a provider cannot cover themselves")
        if covering.person_id == client.person_id:
            raise SelfTreatment("a client cannot cover on their own care team")
        if covered.discipline not in covering.qualifications:
            raise NotQualified(f"the cover must be qualified in {covered.discipline}")
        if any(c.covered_membership_id == covered.id and c.is_live and c.window.overlaps(window) for c in self.coverages):
            raise InvalidCoverage("this membership already has a coverage in that window")
        coverage = Coverage(uuid4(), covered.id, covering.provider_id, window, reason)
        self.coverages.append(coverage)
        self._record(TeamEventType.COVERAGE_SCHEDULED, actor, reason, at, coverage.id)
        return coverage

    def end_coverage(self, actor: PersonId, coverage_id: UUID, reason: str, at: datetime) -> None:
        """Hand back early if it is running; cancel it if it has not started."""
        coverage = next((c for c in self.coverages if c.id == coverage_id), None)
        if coverage is None:
            raise NotFound("no such coverage on this team")
        assert coverage.window.end is not None  # every coverage has an end
        if not coverage.is_live or coverage.window.end <= at:
            raise InvalidCoverage("this coverage is already over")
        self._stop_coverage(coverage, actor, clean_reason(reason), at)

    # ---- Helpers ----

    def _require_own(self, client: ClientFacts) -> None:
        if client.client_id != self.client_id:
            raise ValueError("these client facts are for another client's team")

    def _open_membership(self, membership_id: UUID) -> Membership:
        membership = next((m for m in self.memberships if m.id == membership_id), None)
        if membership is None:
            raise NotFound("no such membership on this team")
        if not membership.period.is_open:
            raise InvalidTiming("that membership has already ended")
        return membership

    def _close(self, membership: Membership, actor: PersonId, reason: str, at: datetime) -> None:
        """Close a membership at t, and with it any coverage still running or yet to start."""
        _require_after_start(membership, at)
        self.memberships[self.memberships.index(membership)] = replace(membership, period=membership.period.close(at))
        for coverage in [c for c in self.coverages if c.covered_membership_id == membership.id]:
            assert coverage.window.end is not None
            if coverage.is_live and coverage.window.end > at:
                self._stop_coverage(coverage, actor, reason, at)

    def _stop_coverage(self, coverage: Coverage, actor: PersonId, reason: str, at: datetime) -> None:
        index = self.coverages.index(coverage)
        if at <= coverage.window.start:
            self.coverages[index] = replace(coverage, cancelled_at=at)
            self._record(TeamEventType.COVERAGE_CANCELLED, actor, reason, at, coverage.id)
        else:
            self.coverages[index] = replace(coverage, window=TimeRange(coverage.window.start, at))
            self._record(TeamEventType.COVERAGE_ENDED, actor, reason, at, coverage.id)

    def _record(self, type: TeamEventType, actor: PersonId, reason: str, at: datetime, subject_id: UUID) -> None:
        self.events.append(TeamEvent(type, actor, reason, at, subject_id))


def _check_org_context(
    provider: ProviderFacts, client: ClientFacts, discipline: Discipline, org: OrganizationId | None
) -> None:
    if org is None:
        if discipline not in provider.qualifications:
            raise NotQualified(f"a solo provider must be qualified in {discipline}")
        return
    if discipline not in provider.practises_at.get(org, frozenset()):
        raise InvalidOrgContext(f"the provider is not a {discipline} practitioner at that org")
    if org not in client.served_by:
        raise InvalidOrgContext("that org does not serve this client")


def _require_after_start(membership: Membership, at: datetime) -> None:
    if at <= membership.period.start:
        raise InvalidTiming("a membership can only change after it started")


def clean_reason(raw: str) -> str:
    reason = raw.strip()
    if not reason or len(reason) > MAX_REASON_LENGTH:
        raise InvalidReason(f"a reason of 1 to {MAX_REASON_LENGTH} characters is required")
    return reason
