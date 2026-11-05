"""Identity use cases: sign up, log in, refresh, log out, authenticate.

Talks only to ports, so it does not know about SQL, argon2 or JWT. Each call runs
inside one transaction opened by the caller (one per HTTP request).
"""

from dataclasses import dataclass
from datetime import datetime

from kinetic.identity.domain.errors import (
    EmailAlreadyRegistered,
    InvalidAccessToken,
    InvalidCredentials,
    InvalidEmail,
    InvalidRefreshToken,
)
from kinetic.identity.domain.model import Account, Email, Person, Session, hash_refresh_token
from kinetic.identity.domain.ports import PasswordHasher
from kinetic.identity.domain.repositories import AccountRepository, PersonRepository, SessionRepository
from kinetic.identity.domain.tokens import AccessClaims, AccessTokenCodec
from kinetic.shared_kernel import Clock, PersonId


@dataclass(frozen=True)
class TokenPair:
    person_id: PersonId
    access_token: str
    access_token_expires_at: datetime
    refresh_token: str


class IdentityService:
    def __init__(
        self,
        persons: PersonRepository,
        accounts: AccountRepository,
        sessions: SessionRepository,
        hasher: PasswordHasher,
        tokens: AccessTokenCodec,
        clock: Clock,
    ) -> None:
        self._persons = persons
        self._accounts = accounts
        self._sessions = sessions
        self._hasher = hasher
        self._tokens = tokens
        self._clock = clock

    def signup(self, full_name: str, email: str, password: str) -> TokenPair:
        """Client self-signup: a new Person with an Account, signed in straight away."""
        at = self._clock.now()
        address = Email.parse(email)
        if self._persons.get_by_email(address) is not None:
            raise EmailAlreadyRegistered(f"{address.value} is already registered")
        person = Person.register(full_name, address, at)
        account = Account.open(person.id, password, self._hasher, at)
        self._persons.add(person)
        self._accounts.add(account)
        return self._start_session(person.id, at)

    def login(self, email: str, password: str) -> TokenPair:
        at = self._clock.now()
        try:
            person = self._persons.get_by_email(Email.parse(email))
        except InvalidEmail:
            person = None
        account = self._accounts.get_by_person(person.id) if person else None
        if account is None:
            # Spend the same argon2 time as a real check, so response time doesn't reveal unknown emails.
            self._hasher.hash(password)
            raise InvalidCredentials("invalid email or password")
        if not account.verify(password, self._hasher):
            raise InvalidCredentials("invalid email or password")
        return self._start_session(account.person_id, at)

    def refresh(self, refresh_token: str) -> TokenPair:
        at = self._clock.now()
        session = self._sessions.get_by_refresh_token_hash(hash_refresh_token(refresh_token))
        if session is None or not session.is_valid_at(at):
            raise InvalidRefreshToken("refresh token is unknown, already used or expired")
        rotated, new_refresh_token = session.rotate()
        if not self._sessions.swap_refresh_token(rotated, expected_hash=session.refresh_token_hash):
            raise InvalidRefreshToken("refresh token is unknown, already used or expired")
        return self._issue(rotated, new_refresh_token, at)

    def logout(self, claims: AccessClaims) -> None:
        self._sessions.delete(claims.session_id)

    def authenticate(self, access_token: str) -> AccessClaims:
        """Stateless: checks the signature and expiry only, never the database."""
        return self._tokens.read(access_token, self._clock.now())

    def find_person_by_email(self, email: str) -> Person | None:
        """For other contexts that know someone by email, e.g. an org adding staff."""
        try:
            return self._persons.get_by_email(Email.parse(email))
        except InvalidEmail:
            return None

    def get_person(self, person_id: PersonId) -> Person:
        person = self._persons.get(person_id)
        if person is None:
            raise InvalidAccessToken("token refers to an unknown person")
        return person

    def _start_session(self, person_id: PersonId, at: datetime) -> TokenPair:
        session, refresh_token = Session.start(person_id, at)
        self._sessions.add(session)
        return self._issue(session, refresh_token, at)

    def _issue(self, session: Session, refresh_token: str, at: datetime) -> TokenPair:
        claims = session.access_claims(at)
        return TokenPair(
            person_id=session.person_id,
            access_token=self._tokens.issue(claims),
            access_token_expires_at=claims.expires_at,
            refresh_token=refresh_token,
        )
