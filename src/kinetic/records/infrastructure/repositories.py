"""SQLAlchemy repository for clinical records. Insert and read only: records are never changed."""

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from kinetic.records.domain.model import ClinicalRecord, RecordCategory
from kinetic.records.infrastructure.tables import ClinicalRecordRow
from kinetic.shared_kernel import ClientId, PersonId


class SqlRecordRepository:
    def __init__(self, db: DbSession) -> None:
        self._db = db

    def add(self, record: ClinicalRecord) -> None:
        self._db.add(
            ClinicalRecordRow(
                id=record.id,
                client_id=record.client_id,
                category=record.category,
                author_id=record.author_id,
                body=record.body,
                written_at=record.written_at,
            )
        )
        self._db.flush()

    def for_client(self, client_id: ClientId) -> list[ClinicalRecord]:
        rows = self._db.scalars(
            select(ClinicalRecordRow)
            .where(ClinicalRecordRow.client_id == client_id)
            .order_by(ClinicalRecordRow.written_at)
        )
        return [
            ClinicalRecord(
                id=row.id,
                client_id=ClientId(row.client_id),
                category=RecordCategory(row.category),
                author_id=PersonId(row.author_id),
                body=row.body,
                written_at=row.written_at,
            )
            for row in rows
        ]
