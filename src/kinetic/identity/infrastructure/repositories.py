"""SQLAlchemy implementations of the identity repositories.

Each one translates between a table row and a domain object, so the domain never
sees SQLAlchemy. SQLAlchemy's Session is imported as DbSession to keep it apart
from the domain's Session.
"""

from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from kinetic.identity.domain.errors import EmailAlreadyRegistered
from kinetic.identity.domain.model import Account, Email, Person, Session
from kinetic.identity.infrastructure.tables import AccountRow, PersonRow, SessionRow
from kinetic.shared_kernel import PersonId, TimeRange


class SqlPersonRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def add(self, person: Person) -> None:
        self._db.add(
            PersonRow(id=person.id, full_name=person.full_name, email=person.email.value, created_at=person.created_at)
        )
        try:
            self._db.flush()
        except IntegrityError as error:
            # The unique constraint on email is the real guarantee: it catches two
            # signups racing past the service's "already registered?" check.
            raise EmailAlreadyRegistered(f"{person.email.value} is already registered") from error

    def get(self, person_id: PersonId) -> Person | None:
        row = self._db.get(PersonRow, person_id)
        return _to_person(row) if row else None

    def get_by_email(self, email: Email) -> Person | None:
        row = self._db.scalar(select(PersonRow).where(PersonRow.email == email.value))
        return _to_person(row) if row else None


class SqlAccountRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def add(self, account: Account) -> None:
        self._db.add(
            AccountRow(
                id=account.id,
                person_id=account.person_id,
                password_hash=account.password_hash,
                created_at=account.created_at,
            )
        )
        self._db.flush()

    def get_by_person(self, person_id: PersonId) -> Account | None:
        row = self._db.scalar(select(AccountRow).where(AccountRow.person_id == person_id))
        if row is None:
            return None
        return Account(
            id=row.id, person_id=PersonId(row.person_id), password_hash=row.password_hash, created_at=row.created_at
        )


class SqlSessionRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def add(self, session: Session) -> None:
        self._db.add(
            SessionRow(
                id=session.id,
                person_id=session.person_id,
                refresh_token_hash=session.refresh_token_hash,
                created_at=session.valid.start,
                expires_at=session.valid.end,
            )
        )
        self._db.flush()

    def get_by_refresh_token_hash(self, refresh_token_hash: str) -> Session | None:
        row = self._db.scalar(select(SessionRow).where(SessionRow.refresh_token_hash == refresh_token_hash))
        if row is None:
            return None
        return Session(
            id=row.id,
            person_id=PersonId(row.person_id),
            refresh_token_hash=row.refresh_token_hash,
            valid=TimeRange(row.created_at, row.expires_at),
        )

    def swap_refresh_token(self, session: Session, expected_hash: str) -> bool:
        # Compare-and-swap in one statement: if two refreshes race, Postgres makes the
        # second wait for the row lock, re-checks the WHERE, and updates 0 rows.
        result = self._db.execute(
            update(SessionRow)
            .where(SessionRow.id == session.id, SessionRow.refresh_token_hash == expected_hash)
            .values(refresh_token_hash=session.refresh_token_hash)
        )
        return result.rowcount == 1

    def delete(self, session_id: UUID) -> None:
        self._db.execute(delete(SessionRow).where(SessionRow.id == session_id))


def _to_person(row: PersonRow) -> Person:
    return Person(id=PersonId(row.id), full_name=row.full_name, email=Email(row.email), created_at=row.created_at)
