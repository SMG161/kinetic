"""access's public module: the only part of access other contexts may import.

Callers use AccessServiceDep and authorize (the enforcement point) with the action and
target types. Fact suppliers implement TeamFacts or PracticeFacts with the view types.
"""

from kinetic.access.api.dependencies import AccessServiceDep, authorize
from kinetic.access.domain.model import (
    Action,
    Decision,
    RecordCategory,
    RecordTarget,
    TeamTarget,
)
from kinetic.access.domain.model import Discipline as AccessDiscipline
from kinetic.access.domain.model import Engagement as AccessEngagement
from kinetic.access.domain.ports import CoverView, MemberView, PracticeFacts, TeamFacts, TeamView

__all__ = [
    "AccessDiscipline",
    "AccessEngagement",
    "AccessServiceDep",
    "Action",
    "CoverView",
    "Decision",
    "MemberView",
    "PracticeFacts",
    "RecordCategory",
    "RecordTarget",
    "TeamFacts",
    "TeamTarget",
    "TeamView",
    "authorize",
]
