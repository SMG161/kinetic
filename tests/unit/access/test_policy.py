"""The policy decision point, with in-memory facts. No database, no other context."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from kinetic.access.application.service import AccessService
from kinetic.access.domain.model import Action, Discipline, Engagement, RecordCategory, RecordTarget, TeamTarget
from kinetic.access.domain.policy import decide
from kinetic.access.domain.ports import CoverView, MemberView, TeamView
from kinetic.shared_kernel import ClientId, FixedClock, OrganizationId, TimeRange, new_person_id

T0 = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
DAY = timedelta(days=1)
NOW = T0 + 12 * DAY  # inside Sam's coverage of Pia
GYM, CLINIC = OrganizationId(uuid4()), OrganizationId(uuid4())
MAYA, ADA, TOM, PIA, SAM, CHEN, MIA, OLD, ALI, EVE = (new_person_id() for _ in range(10))


def member(person, discipline, org=None, engagement=Engagement.ACTIVE, start=T0, end=None) -> MemberView:
    return MemberView(uuid4(), person, discipline, org, engagement, TimeRange(start, end))


M_TOM = member(TOM, Discipline.TRAINER, GYM)
M_PIA = member(PIA, Discipline.PHYSIO)  # solo
M_CHEN = member(CHEN, Discipline.PHYSICIAN, CLINIC)
M_MIA = member(MIA, Discipline.MASSAGE)  # solo
M_OLD = member(OLD, Discipline.PHYSIO, end=T0 + 5 * DAY)  # left the team on day 5
M_ALI = member(ALI, Discipline.TRAINER, engagement=Engagement.ALUMNI)
SAM_COVERS_PIA = CoverView(M_PIA.membership_id, SAM, TimeRange(T0 + 10 * DAY, T0 + 24 * DAY))

TEAM = TeamView(
    client_id=ClientId(uuid4()),
    client_person_id=MAYA,
    members=(M_TOM, M_PIA, M_CHEN, M_MIA, M_OLD, M_ALI),
    covers=(SAM_COVERS_PIA,),
)
LEADS = {GYM: ADA, CLINIC: CHEN}  # Ada leads Maya at the gym; Chen leads her at the clinic


def manage(who, action, membership=None, org=None, at=NOW):
    target = TeamTarget(TEAM.client_id, membership.membership_id if membership else None, org)
    return decide(who, action, target, TEAM, LEADS, at)


def care(who, action, category=None, author=None, at=NOW):
    return decide(who, action, RecordTarget(TEAM.client_id, category, author), TEAM, LEADS, at)


class TestViewingTheTeam:
    @pytest.mark.parametrize("who", [MAYA, TOM, PIA, SAM])
    def test_the_client_members_and_covers_see_the_whole_team(self, who):
        decision = manage(who, Action.VIEW_TEAM)
        assert decision.allowed and decision.scope is None

    def test_a_practice_lead_sees_only_their_orgs_slice(self):
        decision = manage(ADA, Action.VIEW_TEAM)
        assert decision.allowed and decision.scope == frozenset({GYM})

    def test_a_lead_who_also_treats_sees_the_whole_team(self):
        assert manage(CHEN, Action.VIEW_TEAM).scope is None  # Chen is a member as well as a lead

    def test_outsiders_and_former_members_see_nothing(self):
        assert not manage(EVE, Action.VIEW_TEAM).allowed
        assert not manage(OLD, Action.VIEW_TEAM).allowed


class TestManagingMembers:
    def test_each_org_runs_its_own_side(self):
        assert manage(ADA, Action.ADD_MEMBER, org=GYM).allowed
        assert manage(ADA, Action.END_MEMBERSHIP, M_TOM).allowed
        assert manage(ADA, Action.SCHEDULE_COVERAGE, M_TOM).allowed
        assert not manage(ADA, Action.ADD_MEMBER, org=CLINIC).allowed
        assert not manage(ADA, Action.CHANGE_ENGAGEMENT, M_CHEN).allowed  # the clinic's member

    def test_nobody_adds_a_solo_provider_directly(self):
        decision = manage(MAYA, Action.ADD_MEMBER, org=None)
        assert not decision.allowed and "care invitation" in decision.reason

    def test_a_solo_provider_manages_only_their_own_membership(self):
        for action in (Action.CHANGE_ENGAGEMENT, Action.SCHEDULE_COVERAGE, Action.END_COVERAGE, Action.END_MEMBERSHIP):
            assert manage(PIA, action, M_PIA).allowed
        assert not manage(PIA, Action.END_MEMBERSHIP, M_MIA).allowed
        assert not manage(PIA, Action.END_MEMBERSHIP, M_TOM).allowed

    def test_the_client_can_stop_seeing_a_solo_provider_but_not_staff_an_org(self):
        assert manage(MAYA, Action.END_MEMBERSHIP, M_PIA).allowed
        assert not manage(MAYA, Action.CHANGE_ENGAGEMENT, M_PIA).allowed
        assert not manage(MAYA, Action.END_MEMBERSHIP, M_TOM).allowed  # the gym decides its staffing
        assert not manage(MAYA, Action.ADD_MEMBER, org=GYM).allowed

    def test_a_cover_cannot_manage_the_team(self):
        assert not manage(SAM, Action.END_MEMBERSHIP, M_PIA).allowed

    def test_the_client_or_that_orgs_lead_may_discharge_it(self):
        assert manage(MAYA, Action.DISCHARGE_ORGANIZATION, org=GYM).allowed
        assert manage(ADA, Action.DISCHARGE_ORGANIZATION, org=GYM).allowed
        assert not manage(ADA, Action.DISCHARGE_ORGANIZATION, org=CLINIC).allowed
        assert not manage(TOM, Action.DISCHARGE_ORGANIZATION, org=GYM).allowed

    def test_unknown_membership(self):
        decision = decide(ADA, Action.END_MEMBERSHIP, TeamTarget(TEAM.client_id, uuid4()), TEAM, LEADS, NOW)
        assert not decision.allowed and "no such membership" in decision.reason


class TestEngagementDecidesActions:
    @pytest.mark.parametrize("action", [Action.WRITE_NOTE, Action.RUN_SESSION, Action.MESSAGE_CLIENT, Action.BILL])
    def test_active_members_act(self, action):
        assert care(PIA, action, RecordCategory.CLINICAL_NOTE).allowed

    def test_consulting_members_view_and_message_only(self):
        team = TeamView(TEAM.client_id, MAYA, (member(PIA, Discipline.PHYSIO, engagement=Engagement.CONSULTING),), ())
        allowed = {
            a for a in (Action.VIEW_RECORD, Action.WRITE_NOTE, Action.RUN_SESSION, Action.MESSAGE_CLIENT, Action.BILL)
            if decide(PIA, a, RecordTarget(team.client_id, RecordCategory.ASSESSMENT), team, {}, NOW).allowed
        }
        assert allowed == {Action.VIEW_RECORD, Action.MESSAGE_CLIENT}

    def test_alumni_see_only_what_they_wrote(self):
        assert care(ALI, Action.VIEW_RECORD, RecordCategory.TRAINING_PLAN, author=ALI).allowed
        decision = care(ALI, Action.VIEW_RECORD, RecordCategory.TRAINING_PLAN, author=TOM)
        assert not decision.allowed and "only records they wrote" in decision.reason


class TestDisciplineDecidesCategories:
    def test_the_physician_sees_medical_history_and_the_rehab_assessment(self):
        assert care(CHEN, Action.VIEW_RECORD, RecordCategory.MEDICAL_HISTORY).allowed
        assert care(CHEN, Action.VIEW_RECORD, RecordCategory.ASSESSMENT).allowed

    def test_the_massage_therapist_does_not(self):
        decision = care(MIA, Action.VIEW_RECORD, RecordCategory.MEDICAL_HISTORY)
        assert not decision.allowed and "MASSAGE cannot see MEDICAL_HISTORY" in decision.reason
        assert care(MIA, Action.VIEW_RECORD, RecordCategory.SESSION_NOTE).allowed

    def test_the_trainer_sees_the_assessment_summary_not_the_assessment(self):
        assert care(TOM, Action.VIEW_RECORD, RecordCategory.ASSESSMENT_SUMMARY).allowed
        assert not care(TOM, Action.VIEW_RECORD, RecordCategory.ASSESSMENT).allowed

    def test_writing_needs_the_category_too(self):
        assert not care(TOM, Action.WRITE_NOTE, RecordCategory.CLINICAL_NOTE).allowed


class TestCoverage:
    def test_the_cover_acts_as_the_covered_member_during_the_window(self):
        decision = care(SAM, Action.WRITE_NOTE, RecordCategory.CLINICAL_NOTE)
        assert decision.allowed and "covering" in decision.reason

    def test_not_before_the_window(self):
        assert not care(SAM, Action.VIEW_RECORD, RecordCategory.ASSESSMENT, at=T0 + 9 * DAY).allowed

    def test_and_not_after_it_with_the_reason_why(self):
        decision = care(SAM, Action.VIEW_RECORD, RecordCategory.ASSESSMENT, at=T0 + 25 * DAY)
        assert not decision.allowed
        assert decision.reason == f"denied: coverage ended at {(T0 + 24 * DAY).isoformat()}"


class TestEveryoneElse:
    def test_the_client_views_their_records_but_does_not_act_on_them(self):
        assert care(MAYA, Action.VIEW_RECORD, RecordCategory.MEDICAL_HISTORY).allowed
        assert not care(MAYA, Action.WRITE_NOTE, RecordCategory.SESSION_NOTE).allowed

    def test_being_a_practice_lead_grants_no_records(self):
        decision = care(ADA, Action.VIEW_RECORD, RecordCategory.SESSION_NOTE)
        assert not decision.allowed

    def test_a_former_member_is_told_when_their_access_ended(self):
        decision = care(OLD, Action.VIEW_RECORD, RecordCategory.ASSESSMENT)
        assert decision.reason == f"denied: membership ended at {(T0 + 5 * DAY).isoformat()}"

    def test_a_stranger(self):
        assert not care(EVE, Action.VIEW_RECORD, RecordCategory.SESSION_NOTE).allowed

    def test_a_team_action_is_not_a_care_action(self):
        assert not care(PIA, Action.END_MEMBERSHIP).allowed


class TestAccessService:
    class Teams:
        def team(self, client_id):
            return TEAM if client_id == TEAM.client_id else None

    class Practices:
        def leads(self, client_id, at):
            return LEADS if client_id == TEAM.client_id else {}

    def test_it_decides_at_the_clocks_now(self):
        clock = FixedClock(NOW)
        service = AccessService(self.Teams(), self.Practices(), clock)
        target = RecordTarget(TEAM.client_id, RecordCategory.ASSESSMENT)
        assert service.decide(SAM, Action.VIEW_RECORD, target).allowed
        clock.advance(20 * DAY)  # day 32: the coverage is over
        assert not service.decide(SAM, Action.VIEW_RECORD, target).allowed

    def test_it_uses_practice_leads_for_team_actions(self):
        service = AccessService(self.Teams(), self.Practices(), FixedClock(NOW))
        assert service.decide(ADA, Action.VIEW_TEAM, TeamTarget(TEAM.client_id)).scope == frozenset({GYM})

    def test_an_unknown_client_is_denied(self):
        service = AccessService(self.Teams(), self.Practices(), FixedClock(NOW))
        assert not service.decide(MAYA, Action.VIEW_TEAM, TeamTarget(ClientId(uuid4()))).allowed
