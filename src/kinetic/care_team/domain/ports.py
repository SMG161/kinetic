"""What the care team needs from the practice directory, in care_team's own terms."""

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from kinetic.care_team.domain.facts import ClientFacts, ProviderFacts
from kinetic.shared_kernel import ClientId, OrganizationId, PersonId


class ProviderDirectory(Protocol):
    def provider_by_email(self, email: str) -> ProviderFacts | None: ...

    def client(self, client_id: ClientId, at: datetime) -> ClientFacts | None: ...

    def practice_leads(self, client_id: ClientId, at: datetime) -> Mapping[OrganizationId, PersonId]: ...

    def end_relationship(self, org_id: OrganizationId, client_id: ClientId, at: datetime) -> None:
        """Discharge: the org stops serving the client, in the same transaction."""
        ...
