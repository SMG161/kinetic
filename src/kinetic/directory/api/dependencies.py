"""Build the DirectoryService per request.

FastAPI caches dependencies within a request, so this shares get_db's session with
identity: signup creates the person, account and client profile in one transaction.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from kinetic.dependencies import get_clock, get_db
from kinetic.directory.application.services import DirectoryService
from kinetic.directory.infrastructure.people import IdentityPeople
from kinetic.directory.infrastructure.repositories import (
    SqlClientRepository,
    SqlOrganizationRepository,
    SqlProviderRepository,
)
from kinetic.identity.public import IdentityServiceDep
from kinetic.shared_kernel import Clock


def get_directory_service(
    db: Annotated[DbSession, Depends(get_db)],
    clock: Annotated[Clock, Depends(get_clock)],
    identity: IdentityServiceDep,
) -> DirectoryService:
    return DirectoryService(
        organizations=SqlOrganizationRepository(db),
        providers=SqlProviderRepository(db),
        clients=SqlClientRepository(db),
        people=IdentityPeople(identity),
        clock=clock,
    )


DirectoryServiceDep = Annotated[DirectoryService, Depends(get_directory_service)]
