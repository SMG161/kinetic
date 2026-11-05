"""Access tokens: what a signed access token says, and the port that signs and reads it.

The token carries identity only (person_id and session id), never roles or
permissions: those are decided per request by care_team's AccessPolicy, so they
cannot go stale inside a token.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from kinetic.shared_kernel import PersonId

# Short, because a signed token cannot be revoked: logout only stops refreshes.
ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)


@dataclass(frozen=True)
class AccessClaims:
    person_id: PersonId
    session_id: UUID
    expires_at: datetime


class AccessTokenCodec(Protocol):
    def issue(self, claims: AccessClaims) -> str: ...

    def read(self, token: str, at: datetime) -> AccessClaims:
        """Return the claims, or raise InvalidAccessToken if forged, malformed or expired at `at`."""
        ...
