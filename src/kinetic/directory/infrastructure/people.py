"""The People port, answered by identity's public module (directory is downstream of identity)."""

from kinetic.identity.public import IdentityService
from kinetic.shared_kernel import PersonId


class IdentityPeople:
    def __init__(self, identity: IdentityService) -> None:
        self._identity = identity

    def find_by_email(self, email: str) -> PersonId | None:
        person = self._identity.find_person_by_email(email)
        return person.id if person else None
