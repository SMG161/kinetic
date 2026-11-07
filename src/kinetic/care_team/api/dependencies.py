"""Build the care team service per request, on the request's one transaction."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from kinetic.care_team.application.services import CareTeamService
from kinetic.care_team.infrastructure.directory import DirectoryProviders
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
