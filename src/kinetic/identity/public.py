"""identity's public module: the only part of identity other contexts may import.

Everything else under kinetic.identity is internal and can change freely.
"""

from kinetic.identity.api.dependencies import IdentityServiceDep, current_person_id
from kinetic.identity.api.schemas import SignupRequest, TokenResponse
from kinetic.identity.application.services import IdentityService, TokenPair
from kinetic.identity.domain.model import Person

__all__ = [
    "IdentityService",
    "IdentityServiceDep",
    "Person",
    "SignupRequest",
    "TokenPair",
    "TokenResponse",
    "current_person_id",
]
