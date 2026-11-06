"""identity's public module: the only part of identity other contexts may import.

Everything else under kinetic.identity is internal and can change freely.
"""

from kinetic.identity.api.dependencies import IdentityServiceDep, current_person_id, optional_current_person_id
from kinetic.identity.api.schemas import MAX_PASSWORD_LENGTH, SignupRequest, TokenResponse
from kinetic.identity.application.services import IdentityService, TokenPair
from kinetic.identity.domain.model import Email, Person

__all__ = [
    "MAX_PASSWORD_LENGTH",
    "Email",
    "IdentityService",
    "IdentityServiceDep",
    "Person",
    "SignupRequest",
    "TokenPair",
    "TokenResponse",
    "current_person_id",
    "optional_current_person_id",
]
