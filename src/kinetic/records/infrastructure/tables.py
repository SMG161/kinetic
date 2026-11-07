"""How records are stored: a SQLAlchemy table model in the `records` schema.

Must match the hand-written migration. author_id references identity.person in the
database; that foreign key is left out here so this metadata needs no identity models.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class RecordsBase(DeclarativeBase):
    metadata = MetaData(schema="records")
    type_annotation_map = {datetime: DateTime(timezone=True)}


class ClinicalRecordRow(RecordsBase):
    __tablename__ = "clinical_record"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    client_id: Mapped[UUID] = mapped_column(index=True)
    category: Mapped[str]
    author_id: Mapped[UUID]
    body: Mapped[str]
    written_at: Mapped[datetime]
