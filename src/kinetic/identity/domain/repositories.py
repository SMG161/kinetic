"""Repository interfaces: how the application layer loads and saves identity objects.

The SQLAlchemy implementations live in infrastructure/. Nothing here knows about a database.
"""

from typing import Protocol
from uuid import UUID

from kinetic.identity.domain.model import Account, Email, Person, Session
from kinetic.shared_kernel import PersonId


class PersonRepository(Protocol):
    def add(self, person: Person) -> None: ...

    def get(self, person_id: PersonId) -> Person | None: ...

    def get_by_email(self, email: Email) -> Person | None: ...


class AccountRepository(Protocol):
    def add(self, account: Account) -> None: ...

    def get_by_person(self, person_id: PersonId) -> Account | None: ...


class SessionRepository(Protocol):
    def add(self, session: Session) -> None: ...

    def get_by_refresh_token_hash(self, refresh_token_hash: str) -> Session | None: ...

    def swap_refresh_token(self, session: Session, expected_hash: str) -> bool:
        """Store session's new hash only if the current one is still expected_hash.
        Returns False if a concurrent refresh rotated it first."""
        ...

    def delete(self, session_id: UUID) -> None: ...
