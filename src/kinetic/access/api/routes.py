"""/access/explain: may I do this, and why? Answers for the signed-in caller only, since
asking about someone else would reveal who is on whose team."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from kinetic.access.api.dependencies import AccessServiceDep, AccessWiring
from kinetic.access.domain.model import CARE_ACTIONS, Action, RecordCategory, RecordTarget, TeamTarget
from kinetic.access.domain.ports import PracticeFacts, TeamFacts
from kinetic.identity.public import current_person_id
from kinetic.shared_kernel import ClientId, OrganizationId, PersonId

router = APIRouter(tags=["access"])


class DecisionResponse(BaseModel):
    allowed: bool
    reason: str
    scope: list[UUID] | None  # for VIEW_TEAM: the org contexts you may see; null means all


@router.get("/access/explain")
def explain(
    caller: Annotated[PersonId, Depends(current_person_id)],
    access: AccessServiceDep,
    action: Action,
    client_id: UUID,
    membership_id: UUID | None = None,
    org_id: UUID | None = None,
    category: RecordCategory | None = None,
    author_id: UUID | None = None,
) -> DecisionResponse:
    client = ClientId(client_id)
    if action in CARE_ACTIONS:
        target = RecordTarget(client, category, PersonId(author_id) if author_id else None)
    else:
        target = TeamTarget(client, membership_id, OrganizationId(org_id) if org_id else None)
    decision = access.decide(caller, action, target)
    scope = sorted(decision.scope) if decision.scope is not None else None
    return DecisionResponse(allowed=decision.allowed, reason=decision.reason, scope=scope)


def install(
    app: FastAPI,
    team_facts: Callable[[DbSession], TeamFacts],
    practice_facts: Callable[[DbSession], PracticeFacts],
) -> None:
    """Plug access into the app with the contexts' fact adapters; called from main.py."""
    app.state.access_wiring = AccessWiring(team_facts, practice_facts)
    app.include_router(router)
