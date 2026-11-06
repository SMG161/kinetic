"""Invitations: an org bringing someone in as staff, a practitioner or a client.

The token is a secret shown once; only its SHA-256 hash is stored. Accepting applies
the same domain rules as doing it directly (add_staff, add_practitioner, start a
relationship), acting as the inviter, so the inviter's authority is checked again then.
"""

import hashlib
import secrets
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from kinetic.directory.domain.errors import (
    InvalidPracticeLead,
    InvalidStaffRole,
    InvitationNotForYou,
    InvitationUnusable,
    NoDisciplines,
)
from kinetic.directory.domain.model import Discipline, Organization, StaffRole
from kinetic.directory.domain.relationships import clean_reason
from kinetic.shared_kernel import OrganizationId, PersonId, TimeRange

INVITATION_LIFETIME = timedelta(days=7)


class InvitationKind(StrEnum):
    STAFF = "STAFF"
    PRACTITIONER = "PRACTITIONER"
    CLIENT = "CLIENT"


@dataclass(frozen=True)
class Invitation:
    id: UUID
    organization_id: OrganizationId
    invited_by: PersonId
    email: str
    kind: InvitationKind
    role: StaffRole | None  # STAFF only
    disciplines: frozenset[Discipline]  # PRACTITIONER only
    practice_lead: PersonId | None  # CLIENT only
    reason: str | None  # CLIENT only
    token_hash: str
    valid: TimeRange
    accepted_at: datetime | None = None
    accepted_by: PersonId | None = None

    @classmethod
    def for_staff(
        cls, org: Organization, inviter: PersonId, email: str, role: StaffRole, at: datetime
    ) -> tuple["Invitation", str]:
        org.require_manager(inviter)
        if role not in (StaffRole.ADMIN, StaffRole.FRONT_DESK):
            raise InvalidStaffRole(f"staff are invited as ADMIN or FRONT_DESK, not {role}")
        return cls._issue(org, inviter, email, InvitationKind.STAFF, at, role=role)

    @classmethod
    def for_practitioner(
        cls, org: Organization, inviter: PersonId, email: str, disciplines: Iterable[Discipline], at: datetime
    ) -> tuple["Invitation", str]:
        org.require_manager(inviter)
        practised = frozenset(disciplines)
        if not practised:
            raise NoDisciplines("a practitioner practises at least one discipline")
        return cls._issue(org, inviter, email, InvitationKind.PRACTITIONER, at, disciplines=practised)

    @classmethod
    def for_client(
        cls, org: Organization, inviter: PersonId, email: str, practice_lead: PersonId, reason: str, at: datetime
    ) -> tuple["Invitation", str]:
        org.require_manager(inviter)
        if not org.roles_of(practice_lead):
            raise InvalidPracticeLead("the practice lead must be staff of the organization")
        return cls._issue(
            org, inviter, email, InvitationKind.CLIENT, at, practice_lead=practice_lead, reason=clean_reason(reason)
        )

    @classmethod
    def _issue(
        cls,
        org: Organization,
        inviter: PersonId,
        email: str,
        kind: InvitationKind,
        at: datetime,
        role: StaffRole | None = None,
        disciplines: frozenset[Discipline] = frozenset(),
        practice_lead: PersonId | None = None,
        reason: str | None = None,
    ) -> tuple["Invitation", str]:
        """Return the invitation and its plaintext token, shown to the inviter once."""
        token = secrets.token_urlsafe(32)
        invitation = cls(
            id=uuid4(),
            organization_id=org.id,
            invited_by=inviter,
            email=email,
            kind=kind,
            role=role,
            disciplines=disciplines,
            practice_lead=practice_lead,
            reason=reason,
            token_hash=hash_invitation_token(token),
            valid=TimeRange(at, at + INVITATION_LIFETIME),
        )
        return invitation, token

    def check_usable(self, at: datetime) -> None:
        if self.accepted_at is not None:
            raise InvitationUnusable("this invitation has already been used")
        if not self.valid.contains(at):
            raise InvitationUnusable("this invitation has expired")

    def check_acceptable(self, email: str, at: datetime) -> None:
        self.check_usable(at)
        if email != self.email:
            raise InvitationNotForYou("this invitation was sent to a different email")

    def accept(self, person_id: PersonId, at: datetime) -> "Invitation":
        return replace(self, accepted_at=at, accepted_by=person_id)


def hash_invitation_token(token: str) -> str:
    """SHA-256 is enough: the token is 256 random bits, not a guessable password."""
    return hashlib.sha256(token.encode()).hexdigest()
