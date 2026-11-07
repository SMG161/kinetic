"""SQLAlchemy implementations of the directory repositories: rows in, domain objects out."""

from collections.abc import Iterable, Sequence

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from kinetic.directory.domain.errors import AlreadyRegistered, AlreadyServed, AlreadyStaff, ConcurrentChange
from kinetic.directory.domain.invitations import Invitation, InvitationKind
from kinetic.directory.domain.model import Client, Discipline, Organization, Provider, StaffMembership, StaffRole
from kinetic.directory.domain.relationships import ClientRelationship, PracticeLeadAssignment
from kinetic.directory.infrastructure.tables import (
    ClientRelationshipRow,
    ClientRow,
    InvitationRow,
    OrganizationRow,
    PracticeLeadAssignmentRow,
    ProviderRow,
    StaffMembershipRow,
)
from kinetic.shared_kernel import ClientId, OrganizationId, PersonId, ProviderId, TimeRange


class SqlOrganizationRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def add(self, org: Organization) -> None:
        self._db.add(OrganizationRow(id=org.id, name=org.name, created_at=org.created_at))
        self._db.flush()  # the org row must exist before staff rows reference it
        self._insert_staff(org.id, org.staff)

    def get(self, org_id: OrganizationId) -> Organization | None:
        row = self._db.get(OrganizationRow, org_id)
        return self._to_organization(row) if row else None

    def save(self, org: Organization) -> None:
        stored = set(self._db.scalars(select(StaffMembershipRow.id).where(StaffMembershipRow.organization_id == org.id)))
        self._insert_staff(org.id, [m for m in org.staff if m.id not in stored])

    def list_with_staff_member(self, person_id: PersonId) -> list[Organization]:
        org_ids = select(StaffMembershipRow.organization_id).where(StaffMembershipRow.person_id == person_id)
        rows = self._db.scalars(select(OrganizationRow).where(OrganizationRow.id.in_(org_ids)).order_by(OrganizationRow.name))
        return [self._to_organization(row) for row in rows]

    def _insert_staff(self, org_id: OrganizationId, memberships: Iterable[StaffMembership]) -> None:
        self._db.add_all(
            StaffMembershipRow(
                id=m.id,
                organization_id=org_id,
                person_id=m.person_id,
                role=m.role.value,
                disciplines=sorted(m.disciplines),
                created_at=m.created_at,
            )
            for m in memberships
        )
        try:
            self._db.flush()
        except IntegrityError as error:
            # The unique (org, person, role) constraint catches two concurrent adds the domain could not see.
            raise AlreadyStaff("this person already holds that role here") from error

    def _to_organization(self, row: OrganizationRow) -> Organization:
        staff_rows: Sequence[StaffMembershipRow] = self._db.scalars(
            select(StaffMembershipRow)
            .where(StaffMembershipRow.organization_id == row.id)
            .order_by(StaffMembershipRow.created_at)
        ).all()
        staff = [
            StaffMembership(
                id=s.id,
                person_id=PersonId(s.person_id),
                role=StaffRole(s.role),
                disciplines=frozenset(Discipline(d) for d in s.disciplines),
                created_at=s.created_at,
            )
            for s in staff_rows
        ]
        return Organization(id=OrganizationId(row.id), name=row.name, staff=staff, created_at=row.created_at)


class SqlProviderRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def add(self, provider: Provider) -> None:
        self._db.add(
            ProviderRow(
                id=provider.id,
                person_id=provider.person_id,
                qualifications=sorted(provider.qualifications),
                created_at=provider.created_at,
            )
        )
        try:
            self._db.flush()
        except IntegrityError as error:
            raise AlreadyRegistered("this person already has a provider profile") from error

    def get(self, provider_id: ProviderId) -> Provider | None:
        row = self._db.get(ProviderRow, provider_id)
        return _to_provider(row) if row else None

    def get_by_person(self, person_id: PersonId) -> Provider | None:
        row = self._db.scalar(select(ProviderRow).where(ProviderRow.person_id == person_id))
        return _to_provider(row) if row else None


class SqlClientRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def add(self, client: Client) -> None:
        self._db.add(ClientRow(id=client.id, person_id=client.person_id, created_at=client.created_at))
        try:
            self._db.flush()
        except IntegrityError as error:
            raise AlreadyRegistered("this person already has a client profile") from error

    def get(self, client_id: ClientId) -> Client | None:
        row = self._db.get(ClientRow, client_id)
        return _to_client(row) if row else None

    def get_by_person(self, person_id: PersonId) -> Client | None:
        row = self._db.scalar(select(ClientRow).where(ClientRow.person_id == person_id))
        return _to_client(row) if row else None


class SqlClientRelationshipRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def add(self, relationship: ClientRelationship) -> None:
        self._db.add(
            ClientRelationshipRow(
                id=relationship.id,
                organization_id=relationship.organization_id,
                client_id=relationship.client_id,
                valid_from=relationship.period.start,
                valid_to=relationship.period.end,
            )
        )
        try:
            self._db.flush()  # the relationship row must exist before lead rows reference it
        except IntegrityError as error:
            # one_relationship_at_a_time: another request started the same relationship first.
            raise AlreadyServed("this organization already serves this client") from error
        self.save(relationship)

    def get_active(self, org_id: OrganizationId, client_id: ClientId) -> ClientRelationship | None:
        row = self._db.scalar(
            select(ClientRelationshipRow).where(
                ClientRelationshipRow.organization_id == org_id,
                ClientRelationshipRow.client_id == client_id,
                ClientRelationshipRow.valid_to.is_(None),
            )
        )
        return self._to_relationship(row) if row else None

    def list_for_client(self, client_id: ClientId) -> list[ClientRelationship]:
        rows = self._db.scalars(
            select(ClientRelationshipRow)
            .where(ClientRelationshipRow.client_id == client_id)
            .order_by(ClientRelationshipRow.valid_from)
        )
        return [self._to_relationship(row) for row in rows]

    def _to_relationship(self, row: ClientRelationshipRow) -> ClientRelationship:
        lead_rows = self._db.scalars(
            select(PracticeLeadAssignmentRow)
            .where(PracticeLeadAssignmentRow.relationship_id == row.id)
            .order_by(PracticeLeadAssignmentRow.valid_from)
        )
        leads = [
            PracticeLeadAssignment(
                id=lead.id,
                person_id=PersonId(lead.person_id),
                period=TimeRange(lead.valid_from, lead.valid_to),
                reason=lead.reason,
            )
            for lead in lead_rows
        ]
        return ClientRelationship(
            id=row.id,
            organization_id=OrganizationId(row.organization_id),
            client_id=ClientId(row.client_id),
            period=TimeRange(row.valid_from, row.valid_to),
            leads=leads,
        )

    def save(self, relationship: ClientRelationship) -> None:
        for lead in relationship.leads:
            row = self._db.get(PracticeLeadAssignmentRow, lead.id)
            if row is None:
                self._db.add(
                    PracticeLeadAssignmentRow(
                        id=lead.id,
                        relationship_id=relationship.id,
                        person_id=lead.person_id,
                        reason=lead.reason,
                        valid_from=lead.period.start,
                        valid_to=lead.period.end,
                    )
                )
            else:
                row.valid_to = lead.period.end  # periods are only ever closed, never moved
        try:
            self._db.flush()
        except IntegrityError as error:
            # one_lead_at_a_time: a concurrent handoff committed first.
            raise ConcurrentChange("the practice lead was changed by someone else; reload and retry") from error


class SqlInvitationRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def add(self, invitation: Invitation) -> None:
        self._db.add(
            InvitationRow(
                id=invitation.id,
                organization_id=invitation.organization_id,
                invited_by=invitation.invited_by,
                email=invitation.email,
                kind=invitation.kind.value,
                role=invitation.role.value if invitation.role else None,
                disciplines=sorted(invitation.disciplines),
                practice_lead_id=invitation.practice_lead,
                reason=invitation.reason,
                token_hash=invitation.token_hash,
                created_at=invitation.valid.start,
                expires_at=invitation.valid.end,
            )
        )
        self._db.flush()

    def get_by_token_hash(self, token_hash: str) -> Invitation | None:
        row = self._db.scalar(select(InvitationRow).where(InvitationRow.token_hash == token_hash))
        if row is None:
            return None
        return Invitation(
            id=row.id,
            organization_id=OrganizationId(row.organization_id),
            invited_by=PersonId(row.invited_by),
            email=row.email,
            kind=InvitationKind(row.kind),
            role=StaffRole(row.role) if row.role else None,
            disciplines=frozenset(Discipline(d) for d in row.disciplines),
            practice_lead=PersonId(row.practice_lead_id) if row.practice_lead_id else None,
            reason=row.reason,
            token_hash=row.token_hash,
            valid=TimeRange(row.created_at, row.expires_at),
            accepted_at=row.accepted_at,
            accepted_by=PersonId(row.accepted_by) if row.accepted_by else None,
        )

    def mark_accepted(self, invitation: Invitation) -> bool:
        # Compare-and-swap: if two people accept at once, the second waits for the row
        # lock, re-checks "accepted_at IS NULL", and updates nothing.
        result = self._db.execute(
            update(InvitationRow)
            .where(InvitationRow.id == invitation.id, InvitationRow.accepted_at.is_(None))
            .values(accepted_at=invitation.accepted_at, accepted_by=invitation.accepted_by)
        )
        return result.rowcount == 1


def _to_provider(row: ProviderRow) -> Provider:
    return Provider(
        id=ProviderId(row.id),
        person_id=PersonId(row.person_id),
        qualifications=frozenset(Discipline(q) for q in row.qualifications),
        created_at=row.created_at,
    )


def _to_client(row: ClientRow) -> Client:
    return Client(id=ClientId(row.id), person_id=PersonId(row.person_id), created_at=row.created_at)
