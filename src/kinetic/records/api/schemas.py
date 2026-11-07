"""HTTP shapes for records."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from kinetic.records.domain.model import ClinicalRecord, RecordCategory


class WriteRecordRequest(BaseModel):
    category: RecordCategory
    body: str


class RecordResponse(BaseModel):
    id: UUID
    client_id: UUID
    category: RecordCategory
    author_id: UUID
    body: str
    written_at: datetime

    @classmethod
    def of(cls, r: ClinicalRecord) -> "RecordResponse":
        return cls(
            id=r.id, client_id=r.client_id, category=r.category, author_id=r.author_id, body=r.body, written_at=r.written_at
        )
