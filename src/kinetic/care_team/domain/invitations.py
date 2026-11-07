"""Care invitations: a provider asks a client to add them to the client's care team as a
solo member. The client accepting is their consent.

The token is a secret shown once; only its SHA-256 hash is stored. These few lines
mirror directory's invitation tokens on purpose: the shared kernel holds only ids,
Clock, TimeRange and DomainEvent, and contexts never import each other's internals.
"""

import hashlib
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from kinetic.care_team.domain.errors import InvitationNotForYou, InvitationUnusable, NotQualified
from kinetic.care_team.domain.facts import Discipline, ProviderFacts
from kinetic.care_team.domain.model import clean_reason
from kinetic.shared_kernel import PersonId, ProviderId, TimeRange

INVITATION_LIFETIME = timedelta(days=7)


@dataclass(frozen=True)
class CareInvitation:
    id: UUID
    provider_id: ProviderId
    client_email: str
    discipline: Discipline
    reason: str
    token_hash: str
    valid: TimeRange
    accepted_at: datetime | None = None
    accepted_by: PersonId | None = None

    @classmethod
    def issue(
        cls, provider: ProviderFacts, client_email: str, discipline: Discipline, reason: str, at: datetime
    ) -> tuple["CareInvitation", str]:
        """Return the invitation and its plaintext token, shown to the provider once."""
        if discipline not in provider.qualifications:
            raise NotQualified(f"you are not qualified in {discipline}")
        token = secrets.token_urlsafe(32)
        invitation = cls(
            id=uuid4(),
            provider_id=provider.provider_id,
            client_email=client_email,
            discipline=discipline,
            reason=clean_reason(reason),
            token_hash=hash_invitation_token(token),
            valid=TimeRange(at, at + INVITATION_LIFETIME),
        )
        return invitation, token

    def check_acceptable(self, email: str, at: datetime) -> None:
        if self.accepted_at is not None:
            raise InvitationUnusable("this invitation has already been used")
        if not self.valid.contains(at):
            raise InvitationUnusable("this invitation has expired")
        if email != self.client_email:
            raise InvitationNotForYou("this invitation was sent to a different email")

    def accept(self, person_id: PersonId, at: datetime) -> "CareInvitation":
        return replace(self, accepted_at=at, accepted_by=person_id)


def hash_invitation_token(token: str) -> str:
    """SHA-256 is enough: the token is 256 random bits, not a guessable password."""
    return hashlib.sha256(token.encode()).hexdigest()
