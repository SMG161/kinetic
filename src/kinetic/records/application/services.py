"""Records use cases. Access is asked by the endpoint before these run; nothing here decides it."""

from kinetic.records.domain.model import ClinicalRecord, RecordCategory
from kinetic.records.domain.repositories import RecordRepository
from kinetic.shared_kernel import ClientId, Clock, PersonId


class RecordService:
    def __init__(self, records: RecordRepository, clock: Clock) -> None:
        self._records = records
        self._clock = clock

    def write(self, author: PersonId, client_id: ClientId, category: RecordCategory, body: str) -> ClinicalRecord:
        record = ClinicalRecord.write(client_id, author, category, body, self._clock.now())
        self._records.add(record)
        return record

    def for_client(self, client_id: ClientId) -> list[ClinicalRecord]:
        return self._records.for_client(client_id)
