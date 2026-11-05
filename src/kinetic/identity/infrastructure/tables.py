"""How identity is stored: SQLAlchemy table models in the `identity` schema.

These are not the domain classes. Repositories translate between the two, so the
domain never depends on SQLAlchemy. Must match the hand-written migrations.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class IdentityBase(DeclarativeBase):
    metadata = MetaData(schema="identity")
    type_annotation_map = {datetime: DateTime(timezone=True)}


class PersonRow(IdentityBase):
    __tablename__ = "person"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    full_name: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True)
    created_at: Mapped[datetime]


class AccountRow(IdentityBase):
    __tablename__ = "account"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    person_id: Mapped[UUID] = mapped_column(ForeignKey("identity.person.id"), unique=True)
    password_hash: Mapped[str]
    created_at: Mapped[datetime]


class SessionRow(IdentityBase):
    __tablename__ = "session"
    __table_args__ = (CheckConstraint("expires_at > created_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    person_id: Mapped[UUID] = mapped_column(ForeignKey("identity.person.id"))
    token_hash: Mapped[str] = mapped_column(unique=True)
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime]
