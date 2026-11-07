"""Repository interfaces for the care team and care invitations. The SQLAlchemy version lives in infrastructure/."""

from typing import Protocol
from uuid import UUID

from kinetic.care_team.domain.invitations import CareInvitation
from kinetic.care_team.domain.model import CareTeam
from kinetic.shared_kernel import ClientId


class CareTeamRepository(Protocol):
    def add(self, team: CareTeam) -> None:
        """Store a new team. TeamAlreadyExists if the client already has one."""
        ...

    def get(self, team_id: UUID) -> CareTeam | None: ...

    def get_by_client(self, client_id: ClientId) -> CareTeam | None: ...

    def save(self, team: CareTeam) -> None:
        """Persist changes made since the team was loaded. ConcurrentChange if someone saved first."""
        ...


class CareInvitationRepository(Protocol):
    def add(self, invitation: CareInvitation) -> None: ...

    def get_by_token_hash(self, token_hash: str) -> CareInvitation | None: ...

    def mark_accepted(self, invitation: CareInvitation) -> bool:
        """Record the acceptance only if no one accepted first. False if someone did."""
        ...
