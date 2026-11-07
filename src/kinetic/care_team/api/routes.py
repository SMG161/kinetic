"""Care team endpoints. One team per client, so the client id is the team's address.

Every endpoint asks access first (authorize: a denial is 403 with the reason), then
calls the service. None of them decides who may do what.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime

from kinetic.access.public import AccessServiceDep, Action, TeamTarget, authorize
from kinetic.care_team.api.dependencies import CareInvitationServiceDep, CareTeamServiceDep
from kinetic.care_team.api.schemas import (
    AcceptCareInvitationRequest,
    AddMemberRequest,
    CareInvitationRequest,
    CareInvitationResponse,
    ChangeEngagementRequest,
    CoverageResponse,
    HistoryResponse,
    MembershipResponse,
    ReasonRequest,
    ScheduleCoverageRequest,
    TeamResponse,
)
from kinetic.care_team.domain.errors import (
    AlreadyOnTeam,
    CareTeamError,
    ConcurrentChange,
    InvalidCoverage,
    InvalidEngagement,
    InvalidOrgContext,
    InvalidReason,
    InvalidTiming,
    InvitationNotForYou,
    InvitationUnusable,
    NotAClient,
    NotAProvider,
    NotFound,
    NotQualified,
    SelfTreatment,
    TeamAlreadyExists,
)
from kinetic.identity.public import current_person_id
from kinetic.shared_kernel import ClientId, OrganizationId, PersonId

router = APIRouter(prefix="/clients/{client_id}/care-team", tags=["care team"])
invitations = APIRouter(prefix="/care-invitations", tags=["care team"])
CurrentPerson = Annotated[PersonId, Depends(current_person_id)]


@router.get("")
def view_team(
    client_id: UUID,
    me: CurrentPerson,
    access: AccessServiceDep,
    care: CareTeamServiceDep,
    as_of: AwareDatetime | None = None,
) -> TeamResponse:
    """The team at an instant (now by default). A practice lead sees only their org's members."""
    decision = authorize(access, me, Action.VIEW_TEAM, TeamTarget(ClientId(client_id)))
    return TeamResponse.of(care.snapshot(ClientId(client_id), as_of, decision.scope))


@router.get("/history")
def history(client_id: UUID, me: CurrentPerson, access: AccessServiceDep, care: CareTeamServiceDep) -> HistoryResponse:
    decision = authorize(access, me, Action.VIEW_TEAM, TeamTarget(ClientId(client_id)))
    return HistoryResponse.of(care.history(ClientId(client_id), decision.scope))


@router.post("/members", status_code=201)
def add_member(
    client_id: UUID, body: AddMemberRequest, me: CurrentPerson, access: AccessServiceDep, care: CareTeamServiceDep
) -> MembershipResponse:
    org = OrganizationId(body.org_id) if body.org_id else None
    authorize(access, me, Action.ADD_MEMBER, TeamTarget(ClientId(client_id), org_id=org))
    membership = care.add_member(
        me, ClientId(client_id), body.provider_email, body.discipline, org, body.engagement, body.reason
    )
    return MembershipResponse.of(membership)


@router.post("/members/{membership_id}/engagement")
def change_engagement(
    client_id: UUID,
    membership_id: UUID,
    body: ChangeEngagementRequest,
    me: CurrentPerson,
    access: AccessServiceDep,
    care: CareTeamServiceDep,
) -> MembershipResponse:
    authorize(access, me, Action.CHANGE_ENGAGEMENT, TeamTarget(ClientId(client_id), membership_id))
    return MembershipResponse.of(care.change_engagement(me, ClientId(client_id), membership_id, body.engagement, body.reason))


@router.post("/members/{membership_id}/end", status_code=204)
def end_membership(
    client_id: UUID, membership_id: UUID, body: ReasonRequest, me: CurrentPerson, access: AccessServiceDep, care: CareTeamServiceDep
) -> None:
    authorize(access, me, Action.END_MEMBERSHIP, TeamTarget(ClientId(client_id), membership_id))
    care.end_membership(me, ClientId(client_id), membership_id, body.reason)


@router.post("/members/{membership_id}/coverages", status_code=201)
def schedule_coverage(
    client_id: UUID,
    membership_id: UUID,
    body: ScheduleCoverageRequest,
    me: CurrentPerson,
    access: AccessServiceDep,
    care: CareTeamServiceDep,
) -> CoverageResponse:
    authorize(access, me, Action.SCHEDULE_COVERAGE, TeamTarget(ClientId(client_id), membership_id))
    coverage = care.schedule_coverage(
        me, ClientId(client_id), membership_id, body.covering_provider_email, body.starts_at, body.ends_at, body.reason
    )
    return CoverageResponse.of(coverage)


@router.post("/members/{membership_id}/coverages/{coverage_id}/end", status_code=204)
def end_coverage(
    client_id: UUID,
    membership_id: UUID,
    coverage_id: UUID,
    body: ReasonRequest,
    me: CurrentPerson,
    access: AccessServiceDep,
    care: CareTeamServiceDep,
) -> None:
    authorize(access, me, Action.END_COVERAGE, TeamTarget(ClientId(client_id), membership_id))
    care.end_coverage(me, ClientId(client_id), membership_id, coverage_id, body.reason)


@router.post("/orgs/{org_id}/discharge", status_code=204)
def discharge_organization(
    client_id: UUID, org_id: UUID, body: ReasonRequest, me: CurrentPerson, access: AccessServiceDep, care: CareTeamServiceDep
) -> None:
    """The org's members leave the team and its relationship with the client ends, at one instant."""
    authorize(access, me, Action.DISCHARGE_ORGANIZATION, TeamTarget(ClientId(client_id), org_id=OrganizationId(org_id)))
    care.discharge_organization(me, ClientId(client_id), OrganizationId(org_id), body.reason)


@invitations.post("", status_code=201)
def invite_client(body: CareInvitationRequest, me: CurrentPerson, care: CareInvitationServiceDep) -> CareInvitationResponse:
    """A provider invites a client to add them to the client's team as a solo member."""
    return CareInvitationResponse.of(*care.invite(me, body.client_email, body.discipline, body.reason))


@invitations.post("/accept")
def accept_invitation(
    body: AcceptCareInvitationRequest, me: CurrentPerson, access: AccessServiceDep, care: CareInvitationServiceDep
) -> MembershipResponse:
    """The client, signed in, accepts: their consent to the provider joining their team."""
    client_id = care.client_for(me, body.token)
    authorize(access, me, Action.ACCEPT_CARE_INVITATION, TeamTarget(client_id))
    return MembershipResponse.of(care.accept(me, body.token))


_STATUS_FOR = {
    InvalidReason: 422,
    SelfTreatment: 422,
    InvalidOrgContext: 422,
    NotQualified: 422,
    InvalidEngagement: 422,
    InvalidTiming: 422,
    InvalidCoverage: 422,
    NotAClient: 422,
    NotAProvider: 403,
    InvitationNotForYou: 403,
    NotFound: 404,
    AlreadyOnTeam: 409,
    TeamAlreadyExists: 409,
    ConcurrentChange: 409,
    InvitationUnusable: 410,
}


def _care_team_error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=_STATUS_FOR[type(exc)])


def install(app: FastAPI) -> None:
    app.include_router(router)
    app.include_router(invitations)
    app.add_exception_handler(CareTeamError, _care_team_error)
