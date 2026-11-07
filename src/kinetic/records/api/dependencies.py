"""Build the records service per request, on the request's one transaction."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from kinetic.dependencies import get_clock, get_db
from kinetic.records.application.services import RecordService
from kinetic.records.infrastructure.repositories import SqlRecordRepository
from kinetic.shared_kernel import Clock


def get_record_service(
    db: Annotated[DbSession, Depends(get_db)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> RecordService:
    return RecordService(SqlRecordRepository(db), clock)


RecordServiceDep = Annotated[RecordService, Depends(get_record_service)]
