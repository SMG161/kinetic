"""The facts access needs (its policy information points), as ports other contexts implement.

care_team implements TeamFacts and directory implements PracticeFacts; main.py wires
them in. Views are read-only snapshots in access's own vocabulary.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from kinetic.access.domain.model import Discipline, Engagement
from kinetic.shared_kernel import ClientId, OrganizationId, PersonId, TimeRange


@dataclass(frozen=True)
class MemberView:
    membership_id: UUID
    person_id: PersonId  # the provider as a person: the principal is a person
    discipline: Discipline
    org_context: OrganizationId | None
    engagement: Engagement
    period: TimeRange


@dataclass(frozen=True)
class CoverView:
    """A live (not cancelled) coverage."""

    covered_membership_id: UUID
    person_id: PersonId
    window: TimeRange


@dataclass(frozen=True)
class TeamView:
    """A client's care team; empty if the client has no team yet."""

    client_id: ClientId
    client_person_id: PersonId
    members: tuple[MemberView, ...]
    covers: tuple[CoverView, ...]


class TeamFacts(Protocol):
    def team(self, client_id: ClientId) -> TeamView | None:
        """The client's team, empty if they have none yet. None if there is no such client."""
        ...


class PracticeFacts(Protocol):
    def leads(self, client_id: ClientId, at: datetime) -> Mapping[OrganizationId, PersonId]:
        """Each org serving the client at that instant, and its practice lead."""
        ...
