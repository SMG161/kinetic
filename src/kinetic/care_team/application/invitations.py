"""Care invitation use cases: a provider invites a client; the client accepts, signed in.

Accepting is split in two around the access check. The endpoint first asks which
client this acceptance is for (checking the token and the email), then asks access
whether this person may accept for that client, and only then accepts. All of it
runs in the request's one transaction.
"""

from kinetic.care_team.application.services import add_to_team
from kinetic.care_team.domain.errors import InvitationUnusable, NotAClient, NotAProvider, NotFound
from kinetic.care_team.domain.facts import ClientFacts, Discipline
from kinetic.care_team.domain.invitations import CareInvitation, hash_invitation_token
from kinetic.care_team.domain.model import Engagement, Membership
from kinetic.care_team.domain.ports import People, ProviderDirectory
from kinetic.care_team.domain.repositories import CareInvitationRepository, CareTeamRepository
from kinetic.shared_kernel import ClientId, Clock, PersonId


class CareInvitationService:
    def __init__(
        self,
        invitations: CareInvitationRepository,
        teams: CareTeamRepository,
        directory: ProviderDirectory,
        people: People,
        clock: Clock,
    ) -> None:
        self._invitations = invitations
        self._teams = teams
        self._directory = directory
        self._people = people
        self._clock = clock

    def invite(self, inviter: PersonId, client_email: str, discipline: Discipline, reason: str) -> tuple[CareInvitation, str]:
        provider = self._directory.provider_by_person(inviter)
        if provider is None:
            raise NotAProvider("only providers can invite clients onto their care team")
        email = self._people.normalize_email(client_email)
        issued = CareInvitation.issue(provider, email, discipline, reason, self._clock.now())
        self._invitations.add(issued[0])
        return issued

    def client_for(self, person: PersonId, token: str) -> ClientId:
        """Which client this acceptance is for, once the token and email check out."""
        _, client = self._check(person, token)
        return client.client_id

    def accept(self, person: PersonId, token: str) -> Membership:
        """The provider joins the client's team as a solo member, effective now."""
        invitation, client = self._check(person, token)
        at = self._clock.now()
        provider = self._directory.provider(invitation.provider_id)
        if provider is None:
            raise NotFound("the inviting provider no longer exists")
        if not self._invitations.mark_accepted(invitation.accept(person, at)):
            raise InvitationUnusable("this invitation has already been used")
        return add_to_team(
            self._teams, person, provider, client, invitation.discipline, None, Engagement.ACTIVE, invitation.reason, at
        )

    def _check(self, person: PersonId, token: str) -> tuple[CareInvitation, ClientFacts]:
        at = self._clock.now()
        invitation = self._invitations.get_by_token_hash(hash_invitation_token(token))
        if invitation is None:
            raise NotFound("invitation not found")
        invitation.check_acceptable(self._people.email_of(person), at)
        client = self._directory.client_by_person(person, at)
        if client is None:
            raise NotAClient("sign up as a client before accepting a care invitation")
        return invitation, client
