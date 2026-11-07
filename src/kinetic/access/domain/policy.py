"""The policy decision point: given who is asking, what for, and the facts at that instant,
allow or deny, always with a reason. Pure: no I/O, and `at` is passed in.

Two kinds of action. Managing the team follows who may issue which command (each org
runs its own side; the client may always leave). Caring for the client combines two
small tables instead of one matrix: engagement decides the action, discipline decides
the record categories. A cover acts as the membership it covers, during its window only.
"""

from collections.abc import Mapping
from datetime import datetime

from kinetic.access.domain.model import (
    CARE_ACTIONS,
    Action,
    Decision,
    Discipline,
    Engagement,
    RecordCategory,
    RecordTarget,
    Target,
    TeamTarget,
)
from kinetic.access.domain.ports import MemberView, TeamView
from kinetic.shared_kernel import OrganizationId, PersonId

ACTIONS_BY_ENGAGEMENT: Mapping[Engagement, frozenset[Action]] = {
    Engagement.ACTIVE: CARE_ACTIONS,
    Engagement.CONSULTING: frozenset({Action.VIEW_RECORD, Action.MESSAGE_CLIENT}),
    Engagement.ALUMNI: frozenset({Action.VIEW_RECORD}),  # and only records they wrote
}

_CLINICAL = frozenset(
    {
        RecordCategory.MEDICAL_HISTORY,
        RecordCategory.ASSESSMENT,
        RecordCategory.ASSESSMENT_SUMMARY,
        RecordCategory.CLINICAL_NOTE,
        RecordCategory.SESSION_NOTE,
        RecordCategory.TRAINING_PLAN,
    }
)
CATEGORIES_BY_DISCIPLINE: Mapping[Discipline, frozenset[RecordCategory]] = {
    Discipline.PHYSIO: _CLINICAL,
    Discipline.PHYSICIAN: _CLINICAL,
    Discipline.TRAINER: frozenset(
        {RecordCategory.TRAINING_PLAN, RecordCategory.SESSION_NOTE, RecordCategory.ASSESSMENT_SUMMARY}
    ),
    Discipline.MASSAGE: frozenset({RecordCategory.MASSAGE_PLAN, RecordCategory.SESSION_NOTE}),
    Discipline.NUTRITION: frozenset({RecordCategory.NUTRITION_PLAN, RecordCategory.SESSION_NOTE}),
}

OUTSIDER = "not the client, a practice lead or a member of this team"


def decide(
    principal: PersonId,
    action: Action,
    target: Target,
    team: TeamView,
    leads: Mapping[OrganizationId, PersonId],
    at: datetime,
) -> Decision:
    if isinstance(target, TeamTarget):
        return _manage(principal, action, target, team, leads, at)
    return _care(principal, action, target, team, at)


# ---- Managing the team ----


def _manage(
    principal: PersonId,
    action: Action,
    target: TeamTarget,
    team: TeamView,
    leads: Mapping[OrganizationId, PersonId],
    at: datetime,
) -> Decision:
    is_client = principal == team.client_person_id
    led = frozenset(org for org, lead in leads.items() if lead == principal)

    if action is Action.VIEW_TEAM:
        if is_client:
            return Decision.allow("the client sees their whole team")
        if _acting_as(principal, team, at):
            return Decision.allow("members and covers see the whole team")
        if led:
            return Decision.allow("a practice lead sees their own org's members", scope=led)
        return Decision.deny(OUTSIDER)

    if action is Action.DISCHARGE_ORGANIZATION:
        if target.org_id is None:
            return Decision.deny("name the organization to discharge")
        if is_client:
            return Decision.allow("the client may stop any org serving them")
        if target.org_id in led:
            return Decision.allow("practice lead for that org")
        return Decision.deny("only the client or that org's practice lead may discharge it")

    if action is Action.ADD_MEMBER:
        if target.org_id is None:
            return Decision.deny("solo providers join by care invitation")
        if target.org_id in led:
            return Decision.allow("practice lead for that org")
        return Decision.deny("only that org's practice lead adds its members")

    if action not in {Action.CHANGE_ENGAGEMENT, Action.END_MEMBERSHIP, Action.SCHEDULE_COVERAGE, Action.END_COVERAGE}:
        return Decision.deny(f"{action} is not a team action")
    membership = next((m for m in team.members if m.membership_id == target.membership_id), None)
    if membership is None:
        return Decision.deny("no such membership on this team")
    if membership.org_context is not None:
        if membership.org_context in led:
            return Decision.allow("practice lead for this member's org")
        return Decision.deny("only the practice lead for this member's org may do that")
    if principal == membership.person_id:
        return Decision.allow("a solo provider manages their own membership")
    if is_client and action is Action.END_MEMBERSHIP:
        return Decision.allow("the client may stop seeing a solo provider")
    return Decision.deny("only the solo provider manages their own membership")


# ---- Caring for the client ----


def _care(principal: PersonId, action: Action, target: RecordTarget, team: TeamView, at: datetime) -> Decision:
    if action not in CARE_ACTIONS:
        return Decision.deny(f"{action} is not a care action")
    if principal == team.client_person_id:
        if action is Action.VIEW_RECORD:
            return Decision.allow("the client sees their own records")
        return Decision.deny("the client can view their records but not act on them")

    acting = _acting_as(principal, team, at)
    if not acting:
        return Decision.deny(_why_not_on_team(principal, team, at))
    decisions = [_by_tables(principal, action, target, membership, how) for membership, how in acting]
    return next((d for d in decisions if d.allowed), decisions[0])


def _by_tables(
    principal: PersonId, action: Action, target: RecordTarget, membership: MemberView, how: str
) -> Decision:
    if action not in ACTIONS_BY_ENGAGEMENT[membership.engagement]:
        return Decision.deny(f"{membership.engagement} members cannot {action}")
    if action in {Action.VIEW_RECORD, Action.WRITE_NOTE}:
        if target.category is None:
            return Decision.deny("name the record category")
        if target.category not in CATEGORIES_BY_DISCIPLINE[membership.discipline]:
            return Decision.deny(f"{membership.discipline} cannot see {target.category}")
        if membership.engagement is Engagement.ALUMNI and target.author != principal:
            return Decision.deny("ALUMNI members see only records they wrote")
    return Decision.allow(f"{how} ({membership.engagement} {membership.discipline})")


def _acting_as(principal: PersonId, team: TeamView, at: datetime) -> list[tuple[MemberView, str]]:
    """The memberships this person acts through right now: their own, and any they cover."""
    own = [(m, "member") for m in team.members if m.person_id == principal and m.period.contains(at)]
    by_id = {m.membership_id: m for m in team.members}
    covering = [
        (by_id[c.covered_membership_id], "covering")
        for c in team.covers
        if c.person_id == principal and c.window.contains(at) and c.covered_membership_id in by_id
    ]
    return own + covering


def _why_not_on_team(principal: PersonId, team: TeamView, at: datetime) -> str:
    """The most useful reason: when their access ended, if it ever existed."""
    ended_covers = [c.window.end for c in team.covers if c.person_id == principal and c.window.end and c.window.end <= at]
    ended = [m.period.end for m in team.members if m.person_id == principal and m.period.end and m.period.end <= at]
    if ended_covers:
        return f"coverage ended at {max(ended_covers).isoformat()}"
    if ended:
        return f"membership ended at {max(ended).isoformat()}"
    return OUTSIDER
