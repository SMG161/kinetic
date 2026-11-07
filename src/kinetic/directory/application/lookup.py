"""What other contexts may ask of directory. Reports facts and ends a relationship when
told to; never decides access (that is access's job, already done by the caller)."""

from dataclasses import dataclass
from datetime import datetime

from kinetic.directory.domain.errors import NotFound
from kinetic.directory.domain.model import Discipline, StaffRole
from kinetic.directory.domain.repositories import (
    ClientRelationshipRepository,
    ClientRepository,
    OrganizationRepository,
    ProviderRepository,
)
from kinetic.shared_kernel import ClientId, OrganizationId, PersonId, ProviderId


@dataclass(frozen=True)
class ProviderInfo:
    provider_id: ProviderId
    person_id: PersonId
    qualifications: frozenset[Discipline]
    practises_at: dict[OrganizationId, frozenset[Discipline]]


@dataclass(frozen=True)
class ClientInfo:
    client_id: ClientId
    person_id: PersonId
    served_by: frozenset[OrganizationId]


class DirectoryLookup:
    def __init__(
        self,
        providers: ProviderRepository,
        clients: ClientRepository,
        relationships: ClientRelationshipRepository,
        organizations: OrganizationRepository,
    ) -> None:
        self._providers = providers
        self._clients = clients
        self._relationships = relationships
        self._organizations = organizations

    def person_of_provider(self, provider_id: ProviderId) -> PersonId | None:
        provider = self._providers.get(provider_id)
        return provider.person_id if provider else None

    def person_of_client(self, client_id: ClientId) -> PersonId | None:
        client = self._clients.get(client_id)
        return client.person_id if client else None

    def provider_by_person(self, person_id: PersonId) -> ProviderInfo | None:
        provider = self._providers.get_by_person(person_id)
        if provider is None:
            return None
        practises_at = {
            org.id: membership.disciplines
            for org in self._organizations.list_with_staff_member(person_id)
            for membership in org.staff
            if membership.person_id == person_id and membership.role is StaffRole.PRACTITIONER
        }
        return ProviderInfo(provider.id, person_id, provider.qualifications, practises_at)

    def client(self, client_id: ClientId, at: datetime) -> ClientInfo | None:
        client = self._clients.get(client_id)
        if client is None:
            return None
        return ClientInfo(client.id, client.person_id, frozenset(self.practice_leads(client_id, at)))

    def practice_leads(self, client_id: ClientId, at: datetime) -> dict[OrganizationId, PersonId]:
        """Each org serving the client at that instant, and who leads them there."""
        leads = {}
        for relationship in self._relationships.list_for_client(client_id):
            lead = relationship.lead_at(at)
            if lead is not None:
                leads[relationship.organization_id] = lead
        return leads

    def end_relationship(self, org_id: OrganizationId, client_id: ClientId, at: datetime) -> None:
        relationship = self._relationships.get_active(org_id, client_id)
        if relationship is None:
            raise NotFound("that organization does not serve this client")
        relationship.end(at)
        self._relationships.save(relationship)
