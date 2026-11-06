"""Directory HTTP endpoints, including signup and /me, which combine identity with directory.

Identity is upstream and never imports directory, so whatever combines the two lives here.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from kinetic.directory.api.dependencies import DirectoryServiceDep
from kinetic.directory.api.schemas import (
    AddStaffRequest,
    ClientRelationshipResponse,
    CreateOrganizationRequest,
    HandOffPracticeLeadRequest,
    MeResponse,
    OrganizationResponse,
    ProviderResponse,
    RegisterProviderRequest,
    StaffMembershipResponse,
    StartRelationshipRequest,
)
from kinetic.directory.domain.errors import (
    AlreadyRegistered,
    AlreadyServed,
    AlreadyStaff,
    ConcurrentChange,
    DirectoryError,
    InvalidName,
    InvalidPracticeLead,
    InvalidReason,
    InvalidStaffRole,
    NoDisciplines,
    NotAnOrgManager,
    NotFound,
    NotOrgStaff,
    NotQualified,
)
from kinetic.identity.public import IdentityServiceDep, SignupRequest, TokenResponse, current_person_id
from kinetic.shared_kernel import ClientId, OrganizationId, PersonId

router = APIRouter(tags=["directory"])
CurrentPerson = Annotated[PersonId, Depends(current_person_id)]


@router.post("/auth/signup", status_code=201)
def signup(body: SignupRequest, identity: IdentityServiceDep, directory: DirectoryServiceDep) -> TokenResponse:
    """Client self-signup: person, account and client profile, in one transaction."""
    pair = identity.signup(body.full_name, body.email, body.password)
    directory.register_client(pair.person_id)
    return TokenResponse.from_pair(pair)


@router.get("/me")
def me(person_id: CurrentPerson, identity: IdentityServiceDep, directory: DirectoryServiceDep) -> MeResponse:
    return MeResponse.build(identity.get_person(person_id), directory.personas(person_id))


@router.post("/orgs", status_code=201)
def create_organization(
    body: CreateOrganizationRequest, person_id: CurrentPerson, directory: DirectoryServiceDep
) -> OrganizationResponse:
    return OrganizationResponse.from_organization(directory.found_organization(person_id, body.name))


@router.post("/orgs/{org_id}/staff", status_code=201)
def add_staff(
    org_id: UUID, body: AddStaffRequest, person_id: CurrentPerson, directory: DirectoryServiceDep
) -> StaffMembershipResponse:
    membership = directory.add_staff(person_id, OrganizationId(org_id), body.email, body.role, body.disciplines)
    return StaffMembershipResponse.from_membership(membership)


@router.post("/providers", status_code=201)
def register_provider(
    body: RegisterProviderRequest, person_id: CurrentPerson, directory: DirectoryServiceDep
) -> ProviderResponse:
    return ProviderResponse.from_provider(directory.register_provider(person_id, body.qualifications))


@router.post("/orgs/{org_id}/clients", status_code=201)
def start_relationship(
    org_id: UUID, body: StartRelationshipRequest, person_id: CurrentPerson, directory: DirectoryServiceDep
) -> ClientRelationshipResponse:
    relationship = directory.start_relationship(
        person_id, OrganizationId(org_id), body.client_email, body.practice_lead_email, body.reason
    )
    return ClientRelationshipResponse.from_relationship(relationship)


@router.post("/orgs/{org_id}/clients/{client_id}/practice-lead")
def hand_off_practice_lead(
    org_id: UUID,
    client_id: UUID,
    body: HandOffPracticeLeadRequest,
    person_id: CurrentPerson,
    directory: DirectoryServiceDep,
) -> ClientRelationshipResponse:
    relationship = directory.hand_off_practice_lead(
        person_id, OrganizationId(org_id), ClientId(client_id), body.practice_lead_email, body.reason
    )
    return ClientRelationshipResponse.from_relationship(relationship)


@router.get("/orgs/{org_id}/clients/{client_id}")
def get_relationship(
    org_id: UUID, client_id: UUID, person_id: CurrentPerson, directory: DirectoryServiceDep
) -> ClientRelationshipResponse:
    relationship = directory.get_relationship(person_id, OrganizationId(org_id), ClientId(client_id))
    return ClientRelationshipResponse.from_relationship(relationship)


_STATUS_FOR = {
    InvalidName: 422,
    InvalidStaffRole: 422,
    NoDisciplines: 422,
    NotQualified: 422,
    InvalidPracticeLead: 422,
    InvalidReason: 422,
    NotAnOrgManager: 403,
    NotOrgStaff: 403,
    NotFound: 404,
    AlreadyStaff: 409,
    AlreadyRegistered: 409,
    AlreadyServed: 409,
    ConcurrentChange: 409,
}


def _directory_error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=_STATUS_FOR[type(exc)])


def install(app: FastAPI) -> None:
    """Plug the directory context into the app: its routes and its error mapping."""
    app.include_router(router)
    app.add_exception_handler(DirectoryError, _directory_error)
