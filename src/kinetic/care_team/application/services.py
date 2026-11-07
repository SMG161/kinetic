"""Care team use cases. Each runs inside the request's one transaction.

Access has already been decided by the endpoint (through access's enforcement point)
before any method here runs. For views, the endpoint passes the scope access returned,
and this only applies it: it never works out who may see what.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from kinetic.care_team.domain.errors import InvalidTiming, NotFound
from kinetic.care_team.domain.facts import ClientFacts, Discipline, ProviderFacts
from kinetic.care_team.domain.model import CareTeam, Coverage, Engagement, Membership, TeamEvent
from kinetic.care_team.domain.ports import ProviderDirectory
from kinetic.care_team.domain.repositories import CareTeamRepository
from kinetic.shared_kernel import ClientId, Clock, OrganizationId, PersonId, TimeRange

Scope = frozenset[OrganizationId] | None  # None: the whole team


@dataclass(frozen=True)
class TeamSnapshot:
    """The team as it was at one instant, limited to what the viewer may see."""

    client_id: ClientId
    at: datetime
    memberships: list[Membership]
    coverages: list[Coverage]
    practice_leads: Mapping[OrganizationId, PersonId]


@dataclass(frozen=True)
class TeamHistory:
    memberships: list[Membership]
    coverages: list[Coverage]
    events: list[TeamEvent]


class CareTeamService:
    def __init__(self, teams: CareTeamRepository, directory: ProviderDirectory, clock: Clock) -> None:
        self._teams = teams
        self._directory = directory
        self._clock = clock

    # ---- Reading ----

    def snapshot(self, client_id: ClientId, as_of: datetime | None, scope: Scope) -> TeamSnapshot:
        at = as_of or self._clock.now()
        team = self._teams.get_by_client(client_id)
        memberships = [m for m in team.memberships_at(at) if _visible(m, scope)] if team else []
        shown = {m.id for m in memberships}
        coverages = [
            c for c in (team.coverages if team else [])
            if c.covered_membership_id in shown and c.is_live and c.window.end is not None and c.window.end > at
        ]
        leads = {org: lead for org, lead in self._directory.practice_leads(client_id, at).items() if _in(org, scope)}
        return TeamSnapshot(client_id, at, memberships, coverages, leads)

    def history(self, client_id: ClientId, scope: Scope) -> TeamHistory:
        team = self._teams.get_by_client(client_id)
        if team is None:
            return TeamHistory([], [], [])
        org_of = {m.id: m.org_context for m in team.memberships}
        org_of |= {c.id: org_of[c.covered_membership_id] for c in team.coverages}
        memberships = [m for m in team.memberships if _visible(m, scope)]
        coverages = [c for c in team.coverages if scope is None or org_of[c.covered_membership_id] in scope]
        # An event's subject is a membership, a coverage, or (for a discharge) the org itself.
        events = [e for e in team.events if scope is None or org_of.get(e.subject_id, e.subject_id) in scope]
        return TeamHistory(memberships, coverages, events)

    # ---- Commands ----

    def add_member(
        self,
        actor: PersonId,
        client_id: ClientId,
        provider_email: str,
        discipline: Discipline,
        org_id: OrganizationId | None,
        engagement: Engagement,
        reason: str,
    ) -> Membership:
        at = self._clock.now()
        client = self._client(client_id, at)
        provider = self._provider(provider_email)
        return add_to_team(self._teams, actor, provider, client, discipline, org_id, engagement, reason, at)

    def change_engagement(
        self, actor: PersonId, client_id: ClientId, membership_id: UUID, engagement: Engagement, reason: str
    ) -> Membership:
        team = self._team(client_id)
        successor = team.change_engagement(actor, membership_id, engagement, reason, self._clock.now())
        self._teams.save(team)
        return successor

    def end_membership(self, actor: PersonId, client_id: ClientId, membership_id: UUID, reason: str) -> None:
        team = self._team(client_id)
        team.end_membership(actor, membership_id, reason, self._clock.now())
        self._teams.save(team)

    def schedule_coverage(
        self,
        actor: PersonId,
        client_id: ClientId,
        membership_id: UUID,
        covering_email: str,
        starts_at: datetime,
        ends_at: datetime,
        reason: str,
    ) -> Coverage:
        at = self._clock.now()
        team = self._team(client_id)
        covering = self._provider(covering_email)
        try:
            window = TimeRange(starts_at, ends_at)
        except ValueError as error:
            raise InvalidTiming(str(error)) from error
        coverage = team.schedule_coverage(actor, membership_id, covering, self._client(client_id, at), window, reason, at)
        self._teams.save(team)
        return coverage

    def end_coverage(
        self, actor: PersonId, client_id: ClientId, membership_id: UUID, coverage_id: UUID, reason: str
    ) -> None:
        team = self._team(client_id)
        if not any(c.id == coverage_id and c.covered_membership_id == membership_id for c in team.coverages):
            raise NotFound("no such coverage on that membership")
        team.end_coverage(actor, coverage_id, reason, self._clock.now())
        self._teams.save(team)

    def discharge_organization(self, actor: PersonId, client_id: ClientId, org_id: OrganizationId, reason: str) -> None:
        """The org's memberships and its relationship with the client end at the same instant."""
        at = self._clock.now()
        team = self._teams.get_by_client(client_id)
        if team is not None:
            team.discharge_organization(actor, org_id, reason, at)
            self._teams.save(team)
        self._directory.end_relationship(org_id, client_id, at)

    # ---- Helpers ----

    def _team(self, client_id: ClientId) -> CareTeam:
        team = self._teams.get_by_client(client_id)
        if team is None:
            raise NotFound("this client has no care team yet")
        return team

    def _client(self, client_id: ClientId, at: datetime) -> ClientFacts:
        client = self._directory.client(client_id, at)
        if client is None:
            raise NotFound("no such client")
        return client

    def _provider(self, email: str) -> ProviderFacts:
        provider = self._directory.provider_by_email(email)
        if provider is None:
            raise NotFound("no provider is registered with that email")
        return provider


def add_to_team(
    teams: CareTeamRepository,
    actor: PersonId,
    provider: ProviderFacts,
    client: ClientFacts,
    discipline: Discipline,
    org_id: OrganizationId | None,
    engagement: Engagement,
    reason: str,
    at: datetime,
) -> Membership:
    """Add a member; the client's team is created with its first member."""
    team = teams.get_by_client(client.client_id)
    if team is None:
        team = CareTeam.for_client(client)
        membership = team.add_member(actor, provider, client, discipline, org_id, engagement, reason, at)
        teams.add(team)
    else:
        membership = team.add_member(actor, provider, client, discipline, org_id, engagement, reason, at)
        teams.save(team)
    return membership


def _in(org: OrganizationId | None, scope: Scope) -> bool:
    return scope is None or org in scope


def _visible(membership: Membership, scope: Scope) -> bool:
    return _in(membership.org_context, scope)
