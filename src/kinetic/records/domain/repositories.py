"""Repository interface for records. The SQLAlchemy version lives in infrastructure/."""

from typing import Protocol

from kinetic.records.domain.model import ClinicalRecord
from kinetic.shared_kernel import ClientId


class RecordRepository(Protocol):
    def add(self, record: ClinicalRecord) -> None: ...

    def for_client(self, client_id: ClientId) -> list[ClinicalRecord]:
        """Every record about the client, oldest first."""
        ...
