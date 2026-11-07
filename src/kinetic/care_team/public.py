"""care_team's public module: the only part of care_team other contexts may import.

Everything else under kinetic.care_team is internal and can change freely.
"""

from sqlalchemy.orm import Session as DbSession

from kinetic.care_team.infrastructure.access_facts import CareTeamAccessFacts
from kinetic.care_team.infrastructure.repositories import SqlCareTeamRepository
from kinetic.directory.public import directory_lookup


def team_facts(db: DbSession) -> CareTeamAccessFacts:
    """care_team's implementation of access's TeamFacts port, inside the caller's transaction."""
    return CareTeamAccessFacts(SqlCareTeamRepository(db), directory_lookup(db))


__all__ = ["team_facts"]
