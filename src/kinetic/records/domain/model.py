"""A clinical record: one note about a client, in one category, by one author.

Pure Python. Append-only: the business keeps what was written, it does not overwrite it.
records keeps its own RecordCategory; the API translates to access's, so this stays pure.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from kinetic.records.domain.errors import InvalidBody
from kinetic.shared_kernel import ClientId, PersonId

MAX_BODY_LENGTH = 5000


class RecordCategory(StrEnum):
    MEDICAL_HISTORY = "MEDICAL_HISTORY"
    ASSESSMENT = "ASSESSMENT"
    ASSESSMENT_SUMMARY = "ASSESSMENT_SUMMARY"
    CLINICAL_NOTE = "CLINICAL_NOTE"
    SESSION_NOTE = "SESSION_NOTE"
    TRAINING_PLAN = "TRAINING_PLAN"
    MASSAGE_PLAN = "MASSAGE_PLAN"
    NUTRITION_PLAN = "NUTRITION_PLAN"


@dataclass(frozen=True)
class ClinicalRecord:
    id: UUID
    client_id: ClientId
    category: RecordCategory
    author_id: PersonId
    body: str
    written_at: datetime

    @classmethod
    def write(
        cls, client_id: ClientId, author: PersonId, category: RecordCategory, body: str, at: datetime
    ) -> "ClinicalRecord":
        text = body.strip()
        if not text or len(text) > MAX_BODY_LENGTH:
            raise InvalidBody(f"a record needs 1 to {MAX_BODY_LENGTH} characters")
        return cls(uuid4(), client_id, category, author, text, at)
