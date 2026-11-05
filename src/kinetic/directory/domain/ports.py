"""Ports: what directory needs from outside, described in directory's own terms.

Directory is downstream of identity. It needs only "who has this email?", so it
asks that through People; the adapter in infrastructure/ calls identity's public module.
"""

from typing import Protocol

from kinetic.shared_kernel import PersonId


class People(Protocol):
    def find_by_email(self, email: str) -> PersonId | None: ...
