"""Build the care team services per request, on the request's one transaction."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from kinetic.care_team.application.invitations import CareInvitationService
from kinetic.care_team.application.services import CareTeamService
from kinetic.care_team.infrastructure.directory import DirectoryProviders
from kinetic.care_team.infrastructure.invitations import SqlCareInvitationRepository
from kinetic.care_team.infrastructure.people import IdentityPeople
from kinetic.care_team.infrastructure.repositories import SqlCareTeamRepository
from kinetic.dependencies import get_clock, get_db
from kinetic.directory.public import directory_lookup
from kinetic.identity.public import IdentityServiceDep
from kinetic.shared_kernel import Clock


def get_care_team_service(
    db: Annotated[DbSession, Depends(get_db)],
    clock: Annotated[Clock, Depends(get_clock)],
    identity: IdentityServiceDep,
) -> CareTeamService:
    return CareTeamService(SqlCareTeamRepository(db), DirectoryProviders(directory_lookup(db), identity), clock)


CareTeamServiceDep = Annotated[CareTeamService, Depends(get_care_team_service)]


def get_care_invitation_service(
    db: Annotated[DbSession, Depends(get_db)],
    clock: Annotated[Clock, Depends(get_clock)],
    identity: IdentityServiceDep,
) -> CareInvitationService:
    return CareInvitationService(
        SqlCareInvitationRepository(db),
        SqlCareTeamRepository(db),
        DirectoryProviders(directory_lookup(db), identity),
        IdentityPeople(identity),
        clock,
    )


CareInvitationServiceDep = Annotated[CareInvitationService, Depends(get_care_invitation_service)]
