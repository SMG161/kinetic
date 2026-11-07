"""The People port, answered by identity's public module (care_team is downstream of identity)."""

from kinetic.identity.public import Email, IdentityService
from kinetic.shared_kernel import PersonId


class IdentityPeople:
    def __init__(self, identity: IdentityService) -> None:
        self._identity = identity

    def email_of(self, person_id: PersonId) -> str:
        return self._identity.get_person(person_id).email.value

    def normalize_email(self, raw: str) -> str:
        return Email.parse(raw).value
