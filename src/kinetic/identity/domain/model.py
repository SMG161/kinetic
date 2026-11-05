"""Identity model: Person (the human), Account (how they sign in), Session (one sign-in).

Pure Python. Hashing passwords and signing access tokens are ports because they
need libraries; hashing refresh tokens is plain SHA-256 from the standard library.
"""

import hashlib
import re
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from kinetic.identity.domain.errors import InvalidEmail, WeakPassword
from kinetic.identity.domain.ports import PasswordHasher
from kinetic.identity.domain.tokens import ACCESS_TOKEN_LIFETIME, AccessClaims
from kinetic.shared_kernel import PersonId, TimeRange, new_person_id

MIN_PASSWORD_LENGTH = 8
SESSION_LIFETIME = timedelta(days=30)

_EMAIL_SHAPE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


@dataclass(frozen=True)
class Email:
    """Always lowercase, so lookups and the unique constraint ignore case."""

    value: str

    def __post_init__(self) -> None:
        if self.value != self.value.strip().lower() or not _EMAIL_SHAPE.fullmatch(self.value):
            raise InvalidEmail(self.value)

    @classmethod
    def parse(cls, raw: str) -> "Email":
        return cls(raw.strip().lower())


@dataclass
class Person:
    """The real-world human. Exists with or without an Account."""

    id: PersonId
    full_name: str
    email: Email
    created_at: datetime

    @classmethod
    def register(cls, full_name: str, email: Email, at: datetime) -> "Person":
        return cls(id=new_person_id(), full_name=full_name, email=email, created_at=at)


@dataclass
class Account:
    """A way for a Person to sign in: here, a password."""

    id: UUID
    person_id: PersonId
    password_hash: str
    created_at: datetime

    @classmethod
    def open(cls, person_id: PersonId, password: str, hasher: PasswordHasher, at: datetime) -> "Account":
        if len(password) < MIN_PASSWORD_LENGTH:
            raise WeakPassword(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
        return cls(id=uuid4(), person_id=person_id, password_hash=hasher.hash(password), created_at=at)

    def verify(self, password: str, hasher: PasswordHasher) -> bool:
        return hasher.verify(self.password_hash, password)


@dataclass(frozen=True)
class Session:
    """One signed-in device, held by an opaque refresh token.

    Only the refresh token's hash is stored, so a database leak does not leak live
    tokens. Signing out deletes the row: no new access tokens can be issued, and
    the last one expires within ACCESS_TOKEN_LIFETIME.
    """

    id: UUID
    person_id: PersonId
    refresh_token_hash: str
    valid: TimeRange

    @classmethod
    def start(cls, person_id: PersonId, at: datetime) -> tuple["Session", str]:
        """Return the new session and the plaintext refresh token, shown to the caller once."""
        token = _new_refresh_token()
        session = cls(
            id=uuid4(),
            person_id=person_id,
            refresh_token_hash=hash_refresh_token(token),
            valid=TimeRange(at, at + SESSION_LIFETIME),
        )
        return session, token

    def is_valid_at(self, at: datetime) -> bool:
        return self.valid.contains(at)

    def rotate(self) -> tuple["Session", str]:
        """Swap in a new refresh token, so each one works only once."""
        token = _new_refresh_token()
        return replace(self, refresh_token_hash=hash_refresh_token(token)), token

    def access_claims(self, at: datetime) -> AccessClaims:
        return AccessClaims(person_id=self.person_id, session_id=self.id, expires_at=at + ACCESS_TOKEN_LIFETIME)


def _new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """SHA-256 is enough here: refresh tokens are 256 random bits, unlike passwords."""
    return hashlib.sha256(token.encode()).hexdigest()
