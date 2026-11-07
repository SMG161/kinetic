"""Gathers the facts for a decision and asks the policy. The enforcement dependency calls this."""

from kinetic.access.domain.model import Action, Decision, Target, TeamTarget
from kinetic.access.domain.policy import decide
from kinetic.access.domain.ports import PracticeFacts, TeamFacts
from kinetic.shared_kernel import Clock, PersonId


class AccessService:
    def __init__(self, teams: TeamFacts, practices: PracticeFacts, clock: Clock) -> None:
        self._teams = teams
        self._practices = practices
        self._clock = clock

    def decide(self, principal: PersonId, action: Action, target: Target) -> Decision:
        at = self._clock.now()  # decided at request time, so ended windows never linger
        team = self._teams.team(target.team_id)
        if team is None:
            return Decision.deny("no such care team")
        leads = self._practices.leads(team.client_id, at) if isinstance(target, TeamTarget) else {}
        return decide(principal, action, target, team, leads, at)
