"""Ports: what directory needs from outside, described in directory's own terms.

Directory is downstream of identity. It needs to find people by email, know a
person's email, and normalize an email the way identity does; the adapter in
infrastructure/ answers these through identity's public module.
"""

from typing import Protocol

from kinetic.shared_kernel import PersonId


class People(Protocol):
    def find_by_email(self, email: str) -> PersonId | None: ...

    def email_of(self, person_id: PersonId) -> str: ...

    def normalize_email(self, raw: str) -> str:
        """Lowercase and validate; raises identity's InvalidEmail if malformed."""
        ...
