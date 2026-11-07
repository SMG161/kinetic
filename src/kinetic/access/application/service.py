"""Gathers the facts for a decision and asks the policy. The enforcement dependency calls this."""

from collections.abc import Sequence

from kinetic.access.domain.model import Action, Decision, RecordTarget, Target, TeamTarget
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
        team = self._teams.team(target.client_id)
        if team is None:
            return Decision.deny("no such client")
        leads = self._practices.leads(team.client_id, at) if isinstance(target, TeamTarget) else {}
        return decide(principal, action, target, team, leads, at)

    def decide_each(self, principal: PersonId, action: Action, targets: Sequence[RecordTarget]) -> list[Decision]:
        """One decision per record of one client, reading the facts once instead of per record."""
        if len({t.client_id for t in targets}) > 1:
            raise ValueError("decide_each takes records of a single client")
        if not targets:
            return []
        at = self._clock.now()
        team = self._teams.team(targets[0].client_id)
        if team is None:
            return [Decision.deny("no such client")] * len(targets)
        return [decide(principal, action, target, team, {}, at) for target in targets]
