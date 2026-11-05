"""AccessTokenCodec implemented with signed JWTs (PyJWT, HS256)."""

from datetime import UTC, datetime
from uuid import UUID

import jwt

from kinetic.identity.domain.errors import InvalidAccessToken
from kinetic.identity.domain.tokens import AccessClaims
from kinetic.shared_kernel import PersonId

# HS256: one shared secret, fine while this app is the only verifier. If other
# services had to verify tokens, an asymmetric algorithm (ES256) would let them
# check signatures without holding the signing key.
ALGORITHM = "HS256"


class JwtAccessTokenCodec:
    def __init__(self, secret: str) -> None:
        self._secret = secret

    def issue(self, claims: AccessClaims) -> str:
        payload = {"sub": str(claims.person_id), "sid": str(claims.session_id), "exp": claims.expires_at}
        return jwt.encode(payload, self._secret, algorithm=ALGORITHM)

    def read(self, token: str, at: datetime) -> AccessClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                # Pinning the algorithm rejects forged "alg: none" and algorithm-swap tokens.
                algorithms=[ALGORITHM],
                # Expiry is checked below against the injected clock, not the system time.
                options={"verify_exp": False, "require": ["sub", "sid", "exp"]},
            )
            claims = AccessClaims(
                person_id=PersonId(UUID(payload["sub"])),
                session_id=UUID(payload["sid"]),
                expires_at=datetime.fromtimestamp(payload["exp"], UTC),
            )
        except (jwt.InvalidTokenError, ValueError) as error:
            raise InvalidAccessToken("access token is malformed or wrongly signed") from error
        if at >= claims.expires_at:
            raise InvalidAccessToken(f"access token expired at {claims.expires_at.isoformat()}")
        return claims
