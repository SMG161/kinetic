"""Invitation use cases: an org invites someone; they accept, signed in or as a new person.

Invitations are the only way into an org, so every member has consented. Accepting
applies the org's domain methods acting as the inviter, so the inviter's authority is
re-checked.
Everything runs in the request's one transaction: if any rule fails, nothing is
kept and the invitation stays pending.
"""

from collections.abc import Iterable

from kinetic.directory.domain.errors import AlreadyServed, InvitationUnusable, NotFound
from kinetic.directory.domain.invitations import Invitation, InvitationKind, hash_invitation_token
from kinetic.directory.domain.model import Client, Discipline, Organization, Provider, StaffRole
from kinetic.directory.domain.ports import People
from kinetic.directory.domain.relationships import ClientRelationship
from kinetic.directory.domain.repositories import (
    ClientRelationshipRepository,
    ClientRepository,
    InvitationRepository,
    OrganizationRepository,
    ProviderRepository,
)
from kinetic.shared_kernel import Clock, OrganizationId, PersonId


class InvitationService:
    def __init__(
        self,
        invitations: InvitationRepository,
        organizations: OrganizationRepository,
        providers: ProviderRepository,
        clients: ClientRepository,
        relationships: ClientRelationshipRepository,
        people: People,
        clock: Clock,
    ) -> None:
        self._invitations = invitations
        self._organizations = organizations
        self._providers = providers
        self._clients = clients
        self._relationships = relationships
        self._people = people
        self._clock = clock

    def invite_staff(self, inviter: PersonId, org_id: OrganizationId, email: str, role: StaffRole) -> tuple[Invitation, str]:
        org = self._managed_organization(inviter, org_id)
        return self._store(Invitation.for_staff(org, inviter, self._people.normalize_email(email), role, self._clock.now()))

    def invite_practitioner(
        self, inviter: PersonId, org_id: OrganizationId, email: str, disciplines: Iterable[Discipline]
    ) -> tuple[Invitation, str]:
        org = self._managed_organization(inviter, org_id)
        address = self._people.normalize_email(email)
        return self._store(Invitation.for_practitioner(org, inviter, address, disciplines, self._clock.now()))

    def invite_client(
        self, inviter: PersonId, org_id: OrganizationId, email: str, lead_email: str, reason: str
    ) -> tuple[Invitation, str]:
        org = self._managed_organization(inviter, org_id)
        lead = self._people.find_by_email(lead_email)
        if lead is None:
            raise NotFound("no one is registered with the practice lead's email")
        address = self._people.normalize_email(email)
        return self._store(Invitation.for_client(org, inviter, address, lead, reason, self._clock.now()))

    def pending(self, token: str) -> Invitation:
        """The invitation behind a token, if it can still be accepted (by anyone with its email)."""
        invitation = self._invitations.get_by_token_hash(hash_invitation_token(token))
        if invitation is None:
            raise NotFound("invitation not found")
        invitation.check_usable(self._clock.now())
        return invitation

    def accept(self, token: str, person_id: PersonId) -> Invitation:
        at = self._clock.now()
        invitation = self.pending(token)
        invitation.check_acceptable(self._people.email_of(person_id), at)
        accepted = invitation.accept(person_id, at)
        if not self._invitations.mark_accepted(accepted):
            raise InvitationUnusable("this invitation has already been used")

        org = self._organizations.get(invitation.organization_id)
        assert org is not None  # the foreign key guarantees it
        match invitation.kind:
            case InvitationKind.STAFF:
                assert invitation.role is not None
                org.add_staff(invitation.invited_by, person_id, invitation.role, at)
                self._organizations.save(org)
            case InvitationKind.PRACTITIONER:
                provider = self._provider_for(person_id, invitation.disciplines)
                org.add_practitioner(invitation.invited_by, provider, invitation.disciplines, at)
                self._organizations.save(org)
            case InvitationKind.CLIENT:
                self._start_relationship(org, invitation, self._client_for(person_id))
        return accepted

    def _start_relationship(self, org: Organization, invitation: Invitation, client: Client) -> None:
        assert invitation.practice_lead is not None and invitation.reason is not None
        if self._relationships.get_active(org.id, client.id) is not None:
            raise AlreadyServed("this organization already serves this client")
        relationship = ClientRelationship.start(
            org, invitation.invited_by, client, invitation.practice_lead, invitation.reason, self._clock.now()
        )
        self._relationships.add(relationship)

    def _provider_for(self, person_id: PersonId, disciplines: frozenset[Discipline]) -> Provider:
        """An invited practitioner without a provider profile gets one in the invited disciplines."""
        provider = self._providers.get_by_person(person_id)
        if provider is None:
            provider = Provider.register(person_id, disciplines, self._clock.now())
            self._providers.add(provider)
        return provider

    def _client_for(self, person_id: PersonId) -> Client:
        client = self._clients.get_by_person(person_id)
        if client is None:
            client = Client.register(person_id, self._clock.now())
            self._clients.add(client)
        return client

    def _managed_organization(self, actor: PersonId, org_id: OrganizationId) -> Organization:
        org = self._organizations.get(org_id)
        if org is None:
            raise NotFound("organization not found")
        org.require_manager(actor)
        return org

    def _store(self, issued: tuple[Invitation, str]) -> tuple[Invitation, str]:
        self._invitations.add(issued[0])
        return issued
