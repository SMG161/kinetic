"""Records endpoints. Every read and write asks access; records only stores and returns.

Listing asks twice: first whether you may see this client's records at all (so a
refusal comes with its reason), then, for each record, whether its category and
author let you see that one.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from kinetic.access.public import AccessServiceDep, Action, RecordCategory, RecordTarget, authorize
from kinetic.identity.public import current_person_id
from kinetic.records.api.dependencies import RecordServiceDep
from kinetic.records.api.schemas import RecordResponse, WriteRecordRequest
from kinetic.records.domain.errors import InvalidBody, RecordsError
from kinetic.records.domain.model import ClinicalRecord
from kinetic.shared_kernel import ClientId, PersonId

router = APIRouter(prefix="/clients/{client_id}/records", tags=["records"])
CurrentPerson = Annotated[PersonId, Depends(current_person_id)]


def _target(record: ClinicalRecord) -> RecordTarget:
    # records keeps its own category enum; access has its own. They share the values.
    return RecordTarget(record.client_id, RecordCategory(record.category.value), record.author_id)


@router.post("", status_code=201)
def write_record(
    client_id: UUID, body: WriteRecordRequest, me: CurrentPerson, access: AccessServiceDep, records: RecordServiceDep
) -> RecordResponse:
    target = RecordTarget(ClientId(client_id), RecordCategory(body.category.value), me)
    authorize(access, me, Action.WRITE_NOTE, target)
    return RecordResponse.of(records.write(me, ClientId(client_id), body.category, body.body))


@router.get("")
def list_records(
    client_id: UUID, me: CurrentPerson, access: AccessServiceDep, records: RecordServiceDep
) -> list[RecordResponse]:
    """Only the records you may see, oldest first."""
    authorize(access, me, Action.VIEW_RECORD, RecordTarget(ClientId(client_id)))
    all_records = records.for_client(ClientId(client_id))
    decisions = access.decide_each(me, Action.VIEW_RECORD, [_target(r) for r in all_records])
    return [RecordResponse.of(r) for r, decision in zip(all_records, decisions, strict=True) if decision.allowed]


_STATUS_FOR = {InvalidBody: 422}


def _records_error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=_STATUS_FOR[type(exc)])


def install(app: FastAPI) -> None:
    app.include_router(router)
    app.add_exception_handler(RecordsError, _records_error)
