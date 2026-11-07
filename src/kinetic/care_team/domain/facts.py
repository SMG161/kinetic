"""What the care team needs to know from directory, handed in as plain values.

The application layer reads these through the ProviderDirectory port when a command
runs, so the domain checks invariants without knowing directory exists.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from kinetic.shared_kernel import ClientId, OrganizationId, PersonId, ProviderId


class Discipline(StrEnum):
    """care_team's own copy. The port adapter translates directory's, so a rename there stops at the adapter."""

    TRAINER = "TRAINER"
    PHYSIO = "PHYSIO"
    PHYSICIAN = "PHYSICIAN"
    MASSAGE = "MASSAGE"
    NUTRITION = "NUTRITION"


@dataclass(frozen=True)
class ProviderFacts:
    provider_id: ProviderId
    person_id: PersonId
    qualifications: frozenset[Discipline]
    practises_at: Mapping[OrganizationId, frozenset[Discipline]] = field(default_factory=dict)
    """The orgs where they are a practitioner, and in which disciplines there."""


@dataclass(frozen=True)
class ClientFacts:
    client_id: ClientId
    person_id: PersonId
    served_by: frozenset[OrganizationId] = frozenset()
    """The orgs with an active client relationship with this client."""
