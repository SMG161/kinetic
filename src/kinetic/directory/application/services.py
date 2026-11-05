"""Directory use cases. Each call runs inside the caller's transaction (one per HTTP request)."""

from collections.abc import Iterable
from dataclasses import dataclass

from kinetic.directory.domain.errors import AlreadyRegistered, InvalidStaffRole, NotFound
from kinetic.directory.domain.model import Client, Discipline, Organization, Provider, StaffMembership, StaffRole
from kinetic.directory.domain.ports import People
from kinetic.directory.domain.repositories import ClientRepository, OrganizationRepository, ProviderRepository
from kinetic.shared_kernel import Clock, OrganizationId, PersonId


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
        people: People,
        clock: Clock,
    ) -> None:
        self._organizations = organizations
        self._providers = providers
        self._clients = clients
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

    def add_staff(
        self,
        actor: PersonId,
        org_id: OrganizationId,
        email: str,
        role: StaffRole,
        disciplines: Iterable[Discipline],
    ) -> StaffMembership:
        org = self._organizations.get(org_id)
        if org is None:
            raise NotFound("organization not found")
        # Check the actor first, so outsiders cannot probe which emails are registered.
        org.require_manager(actor)
        person_id = self._people.find_by_email(email)
        if person_id is None:
            raise NotFound("no one is registered with that email")
        at = self._clock.now()
        disciplines = list(disciplines)
        if role is StaffRole.PRACTITIONER:
            provider = self._providers.get_by_person(person_id)
            if provider is None:
                raise NotFound("that person has no provider profile")
            membership = org.add_practitioner(actor, provider, disciplines, at)
        elif disciplines:
            raise InvalidStaffRole("only practitioners practise disciplines")
        else:
            membership = org.add_staff(actor, person_id, role, at)
        self._organizations.save(org)
        return membership

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
