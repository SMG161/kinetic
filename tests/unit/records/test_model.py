from datetime import UTC, datetime
from uuid import uuid4

import pytest

from kinetic.records.domain.errors import InvalidBody
from kinetic.records.domain.model import MAX_BODY_LENGTH, ClinicalRecord, RecordCategory
from kinetic.shared_kernel import ClientId, new_person_id

T0 = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)


def write(body: str) -> ClinicalRecord:
    return ClinicalRecord.write(ClientId(uuid4()), new_person_id(), RecordCategory.ASSESSMENT, body, T0)


def test_a_record_keeps_its_text_trimmed():
    assert write("  shoulder: reduced external rotation  ").body == "shoulder: reduced external rotation"


@pytest.mark.parametrize("body", ["", "   ", "x" * (MAX_BODY_LENGTH + 1)])
def test_a_record_needs_some_text_and_not_too_much(body):
    with pytest.raises(InvalidBody):
        write(body)
