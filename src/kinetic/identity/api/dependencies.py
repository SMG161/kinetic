"""FastAPI dependencies: build the IdentityService and resolve who is calling.

current_person_id is how every endpoint learns who the caller is: from the
verified access token, never from the request body.
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session as DbSession

from kinetic.dependencies import get_clock, get_db
from kinetic.identity.application.services import IdentityService
from kinetic.identity.domain.errors import InvalidAccessToken
from kinetic.identity.domain.tokens import AccessClaims
from kinetic.identity.infrastructure.hashing import Argon2PasswordHasher
from kinetic.identity.infrastructure.jwt_codec import JwtAccessTokenCodec
from kinetic.identity.infrastructure.repositories import (
    SqlAccountRepository,
    SqlPersonRepository,
    SqlSessionRepository,
)
from kinetic.settings import get_settings
from kinetic.shared_kernel import Clock, PersonId

_bearer = HTTPBearer(auto_error=False)


def get_identity_service(
    db: Annotated[DbSession, Depends(get_db)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> IdentityService:
    return IdentityService(
        persons=SqlPersonRepository(db),
        accounts=SqlAccountRepository(db),
        sessions=SqlSessionRepository(db),
        hasher=Argon2PasswordHasher(),
        tokens=JwtAccessTokenCodec(get_settings().jwt_secret),
        clock=clock,
    )


IdentityServiceDep = Annotated[IdentityService, Depends(get_identity_service)]


def current_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    service: IdentityServiceDep,
) -> AccessClaims:
    if credentials is None:
        raise InvalidAccessToken("missing bearer token")
    return service.authenticate(credentials.credentials)


def current_person_id(claims: Annotated[AccessClaims, Depends(current_claims)]) -> PersonId:
    return claims.person_id


def optional_current_person_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    service: IdentityServiceDep,
) -> PersonId | None:
    """None when no token is sent. A token that is sent must be valid: a bad one is 401, never anonymous."""
    if credentials is None:
        return None
    return service.authenticate(credentials.credentials).person_id
