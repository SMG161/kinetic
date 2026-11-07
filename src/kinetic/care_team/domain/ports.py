"""What the care team needs from other contexts, in care_team's own terms."""

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from kinetic.care_team.domain.facts import ClientFacts, ProviderFacts
from kinetic.shared_kernel import ClientId, OrganizationId, PersonId, ProviderId


class ProviderDirectory(Protocol):
    def provider(self, provider_id: ProviderId) -> ProviderFacts | None: ...

    def provider_by_person(self, person_id: PersonId) -> ProviderFacts | None: ...

    def provider_by_email(self, email: str) -> ProviderFacts | None: ...

    def client(self, client_id: ClientId, at: datetime) -> ClientFacts | None: ...

    def client_by_person(self, person_id: PersonId, at: datetime) -> ClientFacts | None: ...

    def practice_leads(self, client_id: ClientId, at: datetime) -> Mapping[OrganizationId, PersonId]: ...

    def end_relationship(self, org_id: OrganizationId, client_id: ClientId, at: datetime) -> None:
        """Discharge: the org stops serving the client, in the same transaction."""
        ...


class People(Protocol):
    """Who someone is, from identity."""

    def email_of(self, person_id: PersonId) -> str: ...

    def normalize_email(self, raw: str) -> str:
        """Lowercase and validate, the way identity does; rejects a malformed email."""
        ...
