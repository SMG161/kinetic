"""HTTP request and response shapes for directory. Enums validate roles and disciplines on input."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from kinetic.directory.application.services import Personas, StaffPersona
from kinetic.directory.domain.invitations import Invitation, InvitationKind
from kinetic.directory.domain.model import Discipline, Organization, Provider, StaffMembership, StaffRole
from kinetic.directory.domain.relationships import ClientRelationship, PracticeLeadAssignment
from kinetic.identity.public import MAX_PASSWORD_LENGTH, Person, SignupRequest, TokenResponse


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # fields from another kind are an error, not silently dropped


class StaffInvitationRequest(_Strict):
    kind: Literal[InvitationKind.STAFF]
    email: str
    role: StaffRole


class PractitionerInvitationRequest(_Strict):
    kind: Literal[InvitationKind.PRACTITIONER]
    email: str
    disciplines: list[Discipline]


class ClientInvitationRequest(_Strict):
    kind: Literal[InvitationKind.CLIENT]
    email: str
    practice_lead_email: str
    reason: str


# The "kind" field decides which of the three shapes the body must match.
InvitationRequest = Annotated[
    StaffInvitationRequest | PractitionerInvitationRequest | ClientInvitationRequest, Field(discriminator="kind")
]


class InvitationResponse(BaseModel):
    id: UUID
    kind: InvitationKind
    email: str
    expires_at: datetime
    token: str = Field(description="Shown once. In production this would be emailed, not returned.")

    @classmethod
    def from_issued(cls, invitation: Invitation, token: str) -> "InvitationResponse":
        return cls(
            id=invitation.id, kind=invitation.kind, email=invitation.email, expires_at=invitation.valid.end, token=token
        )


class AcceptInvitationRequest(BaseModel):
    token: str
    full_name: str | None = Field(default=None, min_length=1, max_length=200, description="New people only")
    password: str | None = Field(default=None, max_length=MAX_PASSWORD_LENGTH, description="New people only")


class AcceptedInvitationResponse(BaseModel):
    kind: InvitationKind
    organization_id: UUID
    tokens: TokenResponse | None = Field(description="Set when a new account was created, so you are signed in")


class SignupBody(SignupRequest):
    """Identity's signup fields plus one directory field. Identity never learns what a discipline is."""

    qualifications: list[Discipline] = Field(
        default_factory=list, description="Sign up as a provider in these disciplines; empty means a client"
    )


class CreateOrganizationRequest(BaseModel):
    name: str


class RegisterProviderRequest(BaseModel):
    qualifications: list[Discipline]


class HandOffPracticeLeadRequest(BaseModel):
    practice_lead_email: str
    reason: str


class PracticeLeadResponse(BaseModel):
    person_id: UUID
    reason: str
    valid_from: datetime
    valid_to: datetime | None

    @classmethod
    def from_assignment(cls, a: PracticeLeadAssignment) -> "PracticeLeadResponse":
        return cls(person_id=a.person_id, reason=a.reason, valid_from=a.period.start, valid_to=a.period.end)


class ClientRelationshipResponse(BaseModel):
    id: UUID
    organization_id: UUID
    client_id: UUID
    valid_from: datetime
    practice_lead: PracticeLeadResponse
    lead_history: list[PracticeLeadResponse] = Field(description="Every lead, oldest first")

    @classmethod
    def from_relationship(cls, r: ClientRelationship) -> "ClientRelationshipResponse":
        return cls(
            id=r.id,
            organization_id=r.organization_id,
            client_id=r.client_id,
            valid_from=r.period.start,
            practice_lead=PracticeLeadResponse.from_assignment(r.current_lead),
            lead_history=[PracticeLeadResponse.from_assignment(a) for a in r.leads],
        )


class StaffMembershipResponse(BaseModel):
    id: UUID
    person_id: UUID
    role: StaffRole
    disciplines: list[Discipline]

    @classmethod
    def from_membership(cls, m: StaffMembership) -> "StaffMembershipResponse":
        return cls(id=m.id, person_id=m.person_id, role=m.role, disciplines=sorted(m.disciplines))


class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    staff: list[StaffMembershipResponse]

    @classmethod
    def from_organization(cls, org: Organization) -> "OrganizationResponse":
        return cls(id=org.id, name=org.name, staff=[StaffMembershipResponse.from_membership(m) for m in org.staff])


class ProviderResponse(BaseModel):
    id: UUID
    qualifications: list[Discipline]

    @classmethod
    def from_provider(cls, provider: Provider) -> "ProviderResponse":
        return cls(id=provider.id, qualifications=sorted(provider.qualifications))


class ClientPersona(BaseModel):
    id: UUID


class StaffPersonaResponse(BaseModel):
    organization_id: UUID
    organization_name: str
    role: StaffRole
    disciplines: list[Discipline]

    @classmethod
    def from_persona(cls, persona: StaffPersona) -> "StaffPersonaResponse":
        return cls(
            organization_id=persona.organization.id,
            organization_name=persona.organization.name,
            role=persona.membership.role,
            disciplines=sorted(persona.membership.disciplines),
        )


class MeResponse(BaseModel):
    """Who you are (identity) and everything you are in the business (directory)."""

    id: UUID
    full_name: str
    email: str
    client: ClientPersona | None
    provider: ProviderResponse | None
    staff: list[StaffPersonaResponse]

    @classmethod
    def build(cls, person: Person, personas: Personas) -> "MeResponse":
        return cls(
            id=person.id,
            full_name=person.full_name,
            email=person.email.value,
            client=ClientPersona(id=personas.client.id) if personas.client else None,
            provider=ProviderResponse.from_provider(personas.provider) if personas.provider else None,
            staff=[StaffPersonaResponse.from_persona(p) for p in personas.staff],
        )
