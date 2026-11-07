"""Read-only answers other contexts need from directory. Never decides access; only reports facts."""

from datetime import datetime

from kinetic.directory.domain.repositories import ClientRelationshipRepository, ClientRepository, ProviderRepository
from kinetic.shared_kernel import ClientId, OrganizationId, PersonId, ProviderId


class DirectoryLookup:
    def __init__(
        self,
        providers: ProviderRepository,
        clients: ClientRepository,
        relationships: ClientRelationshipRepository,
    ) -> None:
        self._providers = providers
        self._clients = clients
        self._relationships = relationships

    def person_of_provider(self, provider_id: ProviderId) -> PersonId | None:
        provider = self._providers.get(provider_id)
        return provider.person_id if provider else None

    def person_of_client(self, client_id: ClientId) -> PersonId | None:
        client = self._clients.get(client_id)
        return client.person_id if client else None

    def practice_leads(self, client_id: ClientId, at: datetime) -> dict[OrganizationId, PersonId]:
        """Each org serving the client at that instant, and who leads them there."""
        leads = {}
        for relationship in self._relationships.list_for_client(client_id):
            lead = relationship.lead_at(at)
            if lead is not None:
                leads[relationship.organization_id] = lead
        return leads
