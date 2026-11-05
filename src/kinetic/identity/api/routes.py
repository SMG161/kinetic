"""Identity HTTP endpoints, and the mapping from identity errors to HTTP status codes.

Signup and /me also need directory data (a client profile, personas), so they live
in directory's API: identity is upstream and never imports directory.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from kinetic.identity.api.dependencies import IdentityServiceDep, current_claims
from kinetic.identity.api.schemas import LoginRequest, RefreshRequest, TokenResponse
from kinetic.identity.domain.errors import (
    EmailAlreadyRegistered,
    IdentityError,
    InvalidAccessToken,
    InvalidCredentials,
    InvalidEmail,
    InvalidRefreshToken,
    WeakPassword,
)
from kinetic.identity.domain.tokens import AccessClaims

router = APIRouter(tags=["identity"])


@router.post("/auth/login")
def login(body: LoginRequest, service: IdentityServiceDep) -> TokenResponse:
    return TokenResponse.from_pair(service.login(body.email, body.password))


@router.post("/auth/refresh")
def refresh(body: RefreshRequest, service: IdentityServiceDep) -> TokenResponse:
    return TokenResponse.from_pair(service.refresh(body.refresh_token))


@router.post("/auth/logout", status_code=204)
def logout(claims: Annotated[AccessClaims, Depends(current_claims)], service: IdentityServiceDep) -> None:
    service.logout(claims)


_STATUS_FOR = {
    InvalidEmail: 422,
    WeakPassword: 422,
    EmailAlreadyRegistered: 409,
    InvalidCredentials: 401,
    InvalidAccessToken: 401,
    InvalidRefreshToken: 401,
}


def _identity_error(request: Request, exc: Exception) -> JSONResponse:
    status = _STATUS_FOR[type(exc)]
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse({"detail": str(exc)}, status_code=status, headers=headers)


def install(app: FastAPI) -> None:
    """Plug the identity context into the app: its routes and its error mapping."""
    app.include_router(router)
    app.add_exception_handler(IdentityError, _identity_error)
