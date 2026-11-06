"""Directory model: organizations and their staff, provider profiles, client profiles.

Pure Python. Every profile points at a person_id from identity, and one person can
hold any mix of them: a client who is also a provider, an owner who also treats.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from kinetic.directory.domain.errors import (
    AlreadyStaff,
    InvalidName,
    InvalidStaffRole,
    NoDisciplines,
    NotAnOrgManager,
    NotOrgStaff,
    NotQualified,
)
from kinetic.shared_kernel import ClientId, OrganizationId, PersonId, ProviderId

MAX_NAME_LENGTH = 200


class Discipline(StrEnum):
    TRAINER = "TRAINER"
    PHYSIO = "PHYSIO"
    PHYSICIAN = "PHYSICIAN"
    MASSAGE = "MASSAGE"
    NUTRITION = "NUTRITION"


class StaffRole(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    FRONT_DESK = "FRONT_DESK"
    PRACTITIONER = "PRACTITIONER"


MANAGER_ROLES = frozenset({StaffRole.OWNER, StaffRole.ADMIN})


@dataclass(frozen=True)
class Provider:
    """A professional and what they are qualified in. Independent unless a practitioner somewhere."""

    id: ProviderId
    person_id: PersonId
    qualifications: frozenset[Discipline]
    created_at: datetime

    @classmethod
    def register(cls, person_id: PersonId, qualifications: Iterable[Discipline], at: datetime) -> "Provider":
        qualified = frozenset(qualifications)
        if not qualified:
            raise NoDisciplines("a provider needs at least one discipline")
        return cls(id=ProviderId(uuid4()), person_id=person_id, qualifications=qualified, created_at=at)


@dataclass(frozen=True)
class Client:
    """The profile of someone receiving care."""

    id: ClientId
    person_id: PersonId
    created_at: datetime

    @classmethod
    def register(cls, person_id: PersonId, at: datetime) -> "Client":
        return cls(id=ClientId(uuid4()), person_id=person_id, created_at=at)


@dataclass(frozen=True)
class StaffMembership:
    """One role a person holds at an org. Practitioners also say which disciplines they practise there."""

    id: UUID
    person_id: PersonId
    role: StaffRole
    disciplines: frozenset[Discipline]
    created_at: datetime


@dataclass
class Organization:
    """Aggregate root: an org and its staff. Loaded whole; staff lists are small."""

    id: OrganizationId
    name: str
    staff: list[StaffMembership]
    created_at: datetime

    @classmethod
    def found(cls, name: str, founder: PersonId, at: datetime) -> "Organization":
        """Whoever creates the org becomes its one owner."""
        org = cls(id=OrganizationId(uuid4()), name=_clean_name(name), staff=[], created_at=at)
        org._append(founder, StaffRole.OWNER, frozenset(), at)
        return org

    def roles_of(self, person_id: PersonId) -> set[StaffRole]:
        return {m.role for m in self.staff if m.person_id == person_id}

    def require_manager(self, actor: PersonId) -> None:
        if not self.roles_of(actor) & MANAGER_ROLES:
            raise NotAnOrgManager("only the org's owner or an admin can do this")

    def require_staff(self, person_id: PersonId) -> None:
        if not self.roles_of(person_id):
            raise NotOrgStaff("this person is not staff of the organization")

    def add_staff(self, actor: PersonId, person_id: PersonId, role: StaffRole, at: datetime) -> StaffMembership:
        """Add an admin or front desk member. Owners only come from founding; practitioners from add_practitioner."""
        self.require_manager(actor)
        if role not in (StaffRole.ADMIN, StaffRole.FRONT_DESK):
            raise InvalidStaffRole(f"staff are added as ADMIN or FRONT_DESK, not {role}")
        return self._append(person_id, role, frozenset(), at)

    def add_practitioner(
        self, actor: PersonId, provider: Provider, disciplines: Iterable[Discipline], at: datetime
    ) -> StaffMembership:
        """Add a provider who treats clients on this org's behalf, in some of their disciplines."""
        self.require_manager(actor)
        practised = frozenset(disciplines)
        if not practised:
            raise NoDisciplines("a practitioner practises at least one discipline")
        unqualified = practised - provider.qualifications
        if unqualified:
            raise NotQualified(f"provider is not qualified in {', '.join(sorted(unqualified))}")
        return self._append(provider.person_id, StaffRole.PRACTITIONER, practised, at)

    def _append(
        self, person_id: PersonId, role: StaffRole, disciplines: frozenset[Discipline], at: datetime
    ) -> StaffMembership:
        if role in self.roles_of(person_id):
            raise AlreadyStaff(f"this person is already {role} here")
        membership = StaffMembership(id=uuid4(), person_id=person_id, role=role, disciplines=disciplines, created_at=at)
        self.staff.append(membership)
        return membership


def _clean_name(raw: str) -> str:
    name = raw.strip()
    if not name or len(name) > MAX_NAME_LENGTH:
        raise InvalidName(f"name must be 1 to {MAX_NAME_LENGTH} characters")
    return name
