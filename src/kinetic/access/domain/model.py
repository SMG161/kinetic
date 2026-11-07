"""What a decision is about: the actions, what they target, and the answer.

access keeps its own Discipline and Engagement: it imports no other context, and the
adapters that supply its facts translate into these.
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from kinetic.shared_kernel import OrganizationId, PersonId


class Discipline(StrEnum):
    TRAINER = "TRAINER"
    PHYSIO = "PHYSIO"
    PHYSICIAN = "PHYSICIAN"
    MASSAGE = "MASSAGE"
    NUTRITION = "NUTRITION"


class Engagement(StrEnum):
    ACTIVE = "ACTIVE"
    CONSULTING = "CONSULTING"
    ALUMNI = "ALUMNI"


class RecordCategory(StrEnum):
    MEDICAL_HISTORY = "MEDICAL_HISTORY"
    ASSESSMENT = "ASSESSMENT"
    ASSESSMENT_SUMMARY = "ASSESSMENT_SUMMARY"
    CLINICAL_NOTE = "CLINICAL_NOTE"
    SESSION_NOTE = "SESSION_NOTE"  # non-clinical
    TRAINING_PLAN = "TRAINING_PLAN"
    MASSAGE_PLAN = "MASSAGE_PLAN"
    NUTRITION_PLAN = "NUTRITION_PLAN"


class Action(StrEnum):
    # Managing the team
    VIEW_TEAM = "VIEW_TEAM"
    ADD_MEMBER = "ADD_MEMBER"
    CHANGE_ENGAGEMENT = "CHANGE_ENGAGEMENT"
    END_MEMBERSHIP = "END_MEMBERSHIP"
    SCHEDULE_COVERAGE = "SCHEDULE_COVERAGE"
    END_COVERAGE = "END_COVERAGE"
    DISCHARGE_ORGANIZATION = "DISCHARGE_ORGANIZATION"
    # Caring for the client
    VIEW_RECORD = "VIEW_RECORD"
    WRITE_NOTE = "WRITE_NOTE"
    RUN_SESSION = "RUN_SESSION"
    MESSAGE_CLIENT = "MESSAGE_CLIENT"
    BILL = "BILL"


@dataclass(frozen=True)
class TeamTarget:
    """A team, and for membership actions the membership, or for add/discharge the org."""

    team_id: UUID
    membership_id: UUID | None = None
    org_id: OrganizationId | None = None


@dataclass(frozen=True)
class RecordTarget:
    """Care for the team's client. Viewing or writing a record names its category (and author)."""

    team_id: UUID
    category: RecordCategory | None = None
    author: PersonId | None = None


Target = TeamTarget | RecordTarget


@dataclass(frozen=True)
class Decision:
    """allowed, and always why. For VIEW_TEAM, scope limits what is shown: None is the whole
    team, otherwise only memberships in those org contexts."""

    allowed: bool
    reason: str
    scope: frozenset[OrganizationId] | None = None

    @classmethod
    def allow(cls, reason: str, scope: frozenset[OrganizationId] | None = None) -> "Decision":
        return cls(True, f"allowed: {reason}", scope)

    @classmethod
    def deny(cls, reason: str) -> "Decision":
        return cls(False, f"denied: {reason}")
