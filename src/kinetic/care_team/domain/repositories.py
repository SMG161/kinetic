"""Repository interface for the care team. The SQLAlchemy version lives in infrastructure/."""

from typing import Protocol
from uuid import UUID

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
