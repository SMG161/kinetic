"""Directory use cases. Each call runs inside the caller's transaction (one per HTTP request)."""

from collections.abc import Iterable
from dataclasses import dataclass

from kinetic.directory.domain.errors import AlreadyRegistered, NotFound
from kinetic.directory.domain.model import Client, Discipline, Organization, Provider, StaffMembership
from kinetic.directory.domain.ports import People
from kinetic.directory.domain.relationships import ClientRelationship
from kinetic.directory.domain.repositories import (
    ClientRelationshipRepository,
    ClientRepository,
    OrganizationRepository,
    ProviderRepository,
)
from kinetic.shared_kernel import ClientId, Clock, OrganizationId, PersonId


@dataclass(frozen=True)
class StaffPersona:
    organization: Organization
    membership: StaffMembership


@dataclass(frozen=True)
class Personas:
    """Everything a person is in the business. Any combination is allowed."""

    client: Client | None
    provider: Provider | None
    staff: list[StaffPersona]


class DirectoryService:
    def __init__(
        self,
        organizations: OrganizationRepository,
        providers: ProviderRepository,
        clients: ClientRepository,
        relationships: ClientRelationshipRepository,
        people: People,
        clock: Clock,
    ) -> None:
        self._organizations = organizations
        self._providers = providers
        self._clients = clients
        self._relationships = relationships
        self._people = people
        self._clock = clock

    def register_client(self, person_id: PersonId) -> Client:
        client = Client.register(person_id, self._clock.now())
        self._clients.add(client)
        return client

    def register_provider(self, person_id: PersonId, qualifications: Iterable[Discipline]) -> Provider:
        if self._providers.get_by_person(person_id) is not None:
            raise AlreadyRegistered("you already have a provider profile")
        provider = Provider.register(person_id, qualifications, self._clock.now())
        self._providers.add(provider)
        return provider

    def found_organization(self, founder: PersonId, name: str) -> Organization:
        org = Organization.found(name, founder, self._clock.now())
        self._organizations.add(org)
        return org

    def hand_off_practice_lead(
        self, actor: PersonId, org_id: OrganizationId, client_id: ClientId, lead_email: str, reason: str
    ) -> ClientRelationship:
        org = self._managed_organization(actor, org_id)
        relationship, client = self._active_relationship(org, client_id)
        relationship.hand_off_lead(org, actor, client, self._person_by_email(lead_email), reason, self._clock.now())
        self._relationships.save(relationship)
        return relationship

    def get_relationship(self, viewer: PersonId, org_id: OrganizationId, client_id: ClientId) -> ClientRelationship:
        """Any staff member of the org may see who has been accountable for its client, and why."""
        org = self._organization(org_id)
        org.require_staff(viewer)
        relationship, _ = self._active_relationship(org, client_id)
        return relationship

    def _organization(self, org_id: OrganizationId) -> Organization:
        org = self._organizations.get(org_id)
        if org is None:
            raise NotFound("organization not found")
        return org

    def _managed_organization(self, actor: PersonId, org_id: OrganizationId) -> Organization:
        """Load the org and check the actor manages it, before any lookup that could reveal who exists."""
        org = self._organization(org_id)
        org.require_manager(actor)
        return org

    def _person_by_email(self, email: str) -> PersonId:
        person_id = self._people.find_by_email(email)
        if person_id is None:
            raise NotFound("no one is registered with that email")
        return person_id

    def _active_relationship(self, org: Organization, client_id: ClientId) -> tuple[ClientRelationship, Client]:
        relationship = self._relationships.get_active(org.id, client_id)
        client = self._clients.get(client_id)
        if relationship is None or client is None:
            raise NotFound("this organization does not serve that client")
        return relationship, client

    def personas(self, person_id: PersonId) -> Personas:
        staff = [
            StaffPersona(org, membership)
            for org in self._organizations.list_with_staff_member(person_id)
            for membership in org.staff
            if membership.person_id == person_id
        ]
        return Personas(
            client=self._clients.get_by_person(person_id),
            provider=self._providers.get_by_person(person_id),
            staff=staff,
        )
