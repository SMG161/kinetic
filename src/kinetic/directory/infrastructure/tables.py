"""How directory is stored: SQLAlchemy table models in the `directory` schema.

Must match the hand-written migration. person_id columns reference identity.person
in the database, but the foreign keys are left out here so directory's metadata
never needs identity's table models.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, MetaData, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class DirectoryBase(DeclarativeBase):
    metadata = MetaData(schema="directory")
    type_annotation_map = {datetime: DateTime(timezone=True), list[str]: ARRAY(Text)}


class OrganizationRow(DirectoryBase):
    __tablename__ = "organization"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str]
    created_at: Mapped[datetime]


class StaffMembershipRow(DirectoryBase):
    __tablename__ = "staff_membership"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("directory.organization.id"))
    person_id: Mapped[UUID]
    role: Mapped[str]
    disciplines: Mapped[list[str]]
    created_at: Mapped[datetime]


class ProviderRow(DirectoryBase):
    __tablename__ = "provider"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    person_id: Mapped[UUID] = mapped_column(unique=True)
    qualifications: Mapped[list[str]]
    created_at: Mapped[datetime]


class ClientRow(DirectoryBase):
    __tablename__ = "client"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    person_id: Mapped[UUID] = mapped_column(unique=True)
    created_at: Mapped[datetime]
