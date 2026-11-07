"""The enforcement point (PEP): how endpoints ask access, and how access gets its facts.

access cannot import the contexts that implement its ports, so main.py hands in
factories at startup (install); each request builds the facts on its own transaction.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session as DbSession

from kinetic.access.application.service import AccessService
from kinetic.access.domain.model import Action, Decision, Target
from kinetic.access.domain.ports import PracticeFacts, TeamFacts
from kinetic.dependencies import get_clock, get_db
from kinetic.shared_kernel import Clock, PersonId


@dataclass(frozen=True)
class AccessWiring:
    team_facts: Callable[[DbSession], TeamFacts]
    practice_facts: Callable[[DbSession], PracticeFacts]


def get_access_service(
    request: Request,
    db: Annotated[DbSession, Depends(get_db)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> AccessService:
    wiring: AccessWiring = request.app.state.access_wiring
    return AccessService(wiring.team_facts(db), wiring.practice_facts(db), clock)


AccessServiceDep = Annotated[AccessService, Depends(get_access_service)]


def authorize(access: AccessService, principal: PersonId, action: Action, target: Target) -> Decision:
    """Ask the policy; a denial stops the request with 403 and the reason."""
    decision = access.decide(principal, action, target)
    if not decision.allowed:
        raise HTTPException(403, decision.reason)
    return decision
