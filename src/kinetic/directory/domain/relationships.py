"""Client relationships: an organization serving a client, and who there is accountable for them.

The practice lead is the org's person for this client. They may be non-clinical (a
front desk coordinator), unlike the care team's designations. Lead periods are never
edited, only closed and opened: a handoff closes one at t and opens the next at t.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID, uuid4

from kinetic.directory.domain.errors import InvalidPracticeLead, InvalidReason
from kinetic.directory.domain.model import Client, Organization
from kinetic.shared_kernel import ClientId, OrganizationId, PersonId, TimeRange

MAX_REASON_LENGTH = 500


@dataclass(frozen=True)
class PracticeLeadAssignment:
    id: UUID
    person_id: PersonId
    period: TimeRange
    reason: str


@dataclass
class ClientRelationship:
    """Aggregate root. Invariant: while active, exactly one lead at every instant."""

    id: UUID
    organization_id: OrganizationId
    client_id: ClientId
    period: TimeRange
    leads: list[PracticeLeadAssignment]

    @classmethod
    def start(
        cls, org: Organization, actor: PersonId, client: Client, lead: PersonId, reason: str, at: datetime
    ) -> "ClientRelationship":
        org.require_manager(actor)
        relationship = cls(id=uuid4(), organization_id=org.id, client_id=client.id, period=TimeRange(at), leads=[])
        relationship.leads.append(_assignment(org, client, lead, reason, at))
        return relationship

    @property
    def current_lead(self) -> PracticeLeadAssignment:
        return next(a for a in self.leads if a.period.is_open)

    def lead_at(self, at: datetime) -> PersonId | None:
        """Who was accountable at that instant; None outside the relationship's period."""
        return next((a.person_id for a in self.leads if a.period.contains(at)), None)

    def hand_off_lead(
        self, org: Organization, actor: PersonId, client: Client, new_lead: PersonId, reason: str, at: datetime
    ) -> None:
        org.require_manager(actor)
        current = self.current_lead
        if new_lead == current.person_id:
            raise InvalidPracticeLead("that person is already the practice lead")
        if at <= current.period.start:
            raise InvalidPracticeLead("the lead can only change after the current lead started")
        incoming = _assignment(org, client, new_lead, reason, at)  # validate before changing anything
        self.leads[self.leads.index(current)] = replace(current, period=current.period.close(at))
        self.leads.append(incoming)


def _assignment(org: Organization, client: Client, lead: PersonId, reason: str, at: datetime) -> PracticeLeadAssignment:
    if lead == client.person_id:
        raise InvalidPracticeLead("a client cannot be their own practice lead")
    if not org.roles_of(lead):
        raise InvalidPracticeLead("the practice lead must be staff of the organization")
    return PracticeLeadAssignment(id=uuid4(), person_id=lead, period=TimeRange(at), reason=clean_reason(reason))


def clean_reason(raw: str) -> str:
    reason = raw.strip()
    if not reason or len(reason) > MAX_REASON_LENGTH:
        raise InvalidReason(f"a reason of 1 to {MAX_REASON_LENGTH} characters is required")
    return reason
