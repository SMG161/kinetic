"""SQLAlchemy implementations of the directory repositories: rows in, domain objects out."""

from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from kinetic.directory.domain.errors import AlreadyRegistered, AlreadyStaff
from kinetic.directory.domain.model import Client, Discipline, Organization, Provider, StaffMembership, StaffRole
from kinetic.directory.infrastructure.tables import ClientRow, OrganizationRow, ProviderRow, StaffMembershipRow
from kinetic.shared_kernel import ClientId, OrganizationId, PersonId, ProviderId


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

    def get_by_person(self, person_id: PersonId) -> Provider | None:
        row = self._db.scalar(select(ProviderRow).where(ProviderRow.person_id == person_id))
        if row is None:
            return None
        return Provider(
            id=ProviderId(row.id),
            person_id=PersonId(row.person_id),
            qualifications=frozenset(Discipline(q) for q in row.qualifications),
            created_at=row.created_at,
        )


class SqlClientRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def add(self, client: Client) -> None:
        self._db.add(ClientRow(id=client.id, person_id=client.person_id, created_at=client.created_at))
        try:
            self._db.flush()
        except IntegrityError as error:
            raise AlreadyRegistered("this person already has a client profile") from error

    def get_by_person(self, person_id: PersonId) -> Client | None:
        row = self._db.scalar(select(ClientRow).where(ClientRow.person_id == person_id))
        if row is None:
            return None
        return Client(id=ClientId(row.id), person_id=PersonId(row.person_id), created_at=row.created_at)
