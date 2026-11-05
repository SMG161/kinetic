"""HTTP request and response shapes for directory. Enums validate roles and disciplines on input."""

from uuid import UUID

from pydantic import BaseModel, Field

from kinetic.directory.application.services import Personas, StaffPersona
from kinetic.directory.domain.model import Discipline, Organization, Provider, StaffMembership, StaffRole
from kinetic.identity.public import Person


class CreateOrganizationRequest(BaseModel):
    name: str


class AddStaffRequest(BaseModel):
    email: str
    role: StaffRole
    disciplines: list[Discipline] = Field(default_factory=list, description="Practitioners only")


class RegisterProviderRequest(BaseModel):
    qualifications: list[Discipline]


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
