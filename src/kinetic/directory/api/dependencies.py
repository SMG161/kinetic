"""Build the directory services per request.

FastAPI caches dependencies within a request, so these share get_db's session with
identity: signup creates the person, account and profile in one transaction.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from kinetic.dependencies import get_clock, get_db
from kinetic.directory.application.invitations import InvitationService
from kinetic.directory.application.services import DirectoryService
from kinetic.directory.infrastructure.people import IdentityPeople
from kinetic.directory.infrastructure.repositories import (
    SqlClientRelationshipRepository,
    SqlClientRepository,
    SqlInvitationRepository,
    SqlOrganizationRepository,
    SqlProviderRepository,
)
from kinetic.identity.public import IdentityServiceDep
from kinetic.shared_kernel import Clock

DbDep = Annotated[DbSession, Depends(get_db)]
ClockDep = Annotated[Clock, Depends(get_clock)]


def get_directory_service(db: DbDep, clock: ClockDep, identity: IdentityServiceDep) -> DirectoryService:
    return DirectoryService(
        organizations=SqlOrganizationRepository(db),
        providers=SqlProviderRepository(db),
        clients=SqlClientRepository(db),
        relationships=SqlClientRelationshipRepository(db),
        people=IdentityPeople(identity),
        clock=clock,
    )


def get_invitation_service(db: DbDep, clock: ClockDep, identity: IdentityServiceDep) -> InvitationService:
    return InvitationService(
        invitations=SqlInvitationRepository(db),
        organizations=SqlOrganizationRepository(db),
        providers=SqlProviderRepository(db),
        clients=SqlClientRepository(db),
        relationships=SqlClientRelationshipRepository(db),
        people=IdentityPeople(identity),
        clock=clock,
    )


DirectoryServiceDep = Annotated[DirectoryService, Depends(get_directory_service)]
InvitationServiceDep = Annotated[InvitationService, Depends(get_invitation_service)]
