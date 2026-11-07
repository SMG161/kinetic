"""The care team's invariants, and the brief's scenarios at the domain level. No database."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from kinetic.care_team.domain.errors import (
    AlreadyOnTeam,
    InvalidCoverage,
    InvalidEngagement,
    InvalidOrgContext,
    InvalidReason,
    InvalidTiming,
    NotFound,
    NotQualified,
    SelfTreatment,
)
from kinetic.care_team.domain.facts import ClientFacts, Discipline, ProviderFacts
from kinetic.care_team.domain.model import CareTeam, Engagement, TeamEventType
from kinetic.shared_kernel import ClientId, OrganizationId, ProviderId, TimeRange, new_person_id

T0 = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
DAY = timedelta(days=1)
GYM, CLINIC = OrganizationId(uuid4()), OrganizationId(uuid4())
ADA = new_person_id()  # IronWorks' practice lead for Maya; the actor in most commands

MAYA = ClientFacts(ClientId(uuid4()), new_person_id(), served_by=frozenset({GYM, CLINIC}))


def provider(discipline: Discipline, practises_at: OrganizationId | None = None) -> ProviderFacts:
    """A provider qualified in one discipline, and a practitioner in it at one org if given."""
    orgs = {practises_at: frozenset({discipline})} if practises_at else {}
    return ProviderFacts(ProviderId(uuid4()), new_person_id(), frozenset({discipline}), orgs)


TOM = provider(Discipline.TRAINER, GYM)  # gym trainer
PIA = provider(Discipline.PHYSIO)  # solo physio
SAM = provider(Discipline.PHYSIO)  # solo physio, Pia's colleague
CHEN = provider(Discipline.PHYSICIAN, CLINIC)  # clinic physician
MIA = provider(Discipline.MASSAGE)  # solo massage therapist


@pytest.fixture
def team() -> CareTeam:
    return CareTeam.for_client(MAYA)


def add(team: CareTeam, who: ProviderFacts, discipline: Discipline, org=None, at=T0, engagement=Engagement.ACTIVE):
    return team.add_member(ADA, who, MAYA, discipline, org, engagement, f"{discipline} for Maya", at)


class TestAddingMembers:
    def test_a_gym_trainer_joins_in_the_gyms_context(self, team):
        tom = add(team, TOM, Discipline.TRAINER, GYM)
        assert (tom.org_context, tom.engagement, tom.period.is_open) == (GYM, Engagement.ACTIVE, True)

    def test_a_solo_provider_joins_with_no_org_context(self, team):
        assert add(team, PIA, Discipline.PHYSIO).org_context is None

    def test_a_solo_provider_must_be_qualified(self, team):
        with pytest.raises(NotQualified):
            add(team, MIA, Discipline.PHYSIO)

    def test_the_org_must_employ_them_in_that_discipline(self, team):
        with pytest.raises(InvalidOrgContext):
            add(team, TOM, Discipline.TRAINER, CLINIC)  # Tom works at the gym, not the clinic
        with pytest.raises(InvalidOrgContext):
            add(team, PIA, Discipline.PHYSIO, GYM)  # Pia is solo

    def test_the_org_must_serve_the_client(self, team):
        stranger = ClientFacts(ClientId(uuid4()), new_person_id(), served_by=frozenset())
        other_team = CareTeam.for_client(stranger)
        with pytest.raises(InvalidOrgContext, match="does not serve"):
            other_team.add_member(ADA, TOM, stranger, Discipline.TRAINER, GYM, Engagement.ACTIVE, "r", T0)

    def test_nobody_joins_as_alumni(self, team):
        with pytest.raises(InvalidEngagement):
            add(team, PIA, Discipline.PHYSIO, engagement=Engagement.ALUMNI)

    def test_a_member_can_join_as_consulting(self, team):
        assert add(team, CHEN, Discipline.PHYSICIAN, CLINIC, engagement=Engagement.CONSULTING).engagement is Engagement.CONSULTING

    def test_a_reason_is_required(self, team):
        with pytest.raises(InvalidReason):
            team.add_member(ADA, PIA, MAYA, Discipline.PHYSIO, None, Engagement.ACTIVE, "  ", T0)

    def test_facts_for_another_client_are_refused(self, team):
        stranger = ClientFacts(ClientId(uuid4()), new_person_id())
        with pytest.raises(ValueError):
            team.add_member(ADA, PIA, stranger, Discipline.PHYSIO, None, Engagement.ACTIVE, "r", T0)


class TestInvariant2NoOverlappingMemberships:
    def test_a_provider_is_on_the_team_once_at_a_time(self, team):
        add(team, PIA, Discipline.PHYSIO)
        with pytest.raises(AlreadyOnTeam):
            add(team, PIA, Discipline.PHYSIO, at=T0 + DAY)

    def test_they_can_rejoin_from_the_instant_they_left(self, team):
        """A physio leaves the gym, goes solo and keeps the client: end and add at the same t."""
        gym_physio = provider(Discipline.PHYSIO, GYM)
        at_gym = add(team, gym_physio, Discipline.PHYSIO, GYM)
        team.end_membership(ADA, at_gym.id, "leaving the gym", T0 + 30 * DAY)
        solo = add(team, gym_physio, Discipline.PHYSIO, at=T0 + 30 * DAY)
        assert solo.org_context is None
        assert [m.org_context for m in team.memberships] == [GYM, None]


class TestInvariant3PeriodsAreClosedNotEdited:
    def test_stepping_back_closes_one_period_and_opens_the_next_at_the_same_instant(self, team):
        active = add(team, PIA, Discipline.PHYSIO)
        consulting = team.change_engagement(ADA, active.id, Engagement.CONSULTING, "rehab finished", T0 + 60 * DAY)

        old, new = team.memberships
        assert old.engagement is Engagement.ACTIVE and old.period.end == T0 + 60 * DAY
        assert new == consulting and new.period.start == T0 + 60 * DAY and new.period.is_open
        assert new.reason == "rehab finished"

    def test_the_same_engagement_is_not_a_change(self, team):
        active = add(team, PIA, Discipline.PHYSIO)
        with pytest.raises(InvalidEngagement):
            team.change_engagement(ADA, active.id, Engagement.ACTIVE, "r", T0 + DAY)

    def test_a_change_must_come_after_the_period_started(self, team):
        active = add(team, PIA, Discipline.PHYSIO, at=T0 + DAY)
        with pytest.raises(InvalidTiming):
            team.change_engagement(ADA, active.id, Engagement.CONSULTING, "r", T0)
        assert team.memberships == [active]  # nothing changed

    def test_an_ended_membership_cannot_change(self, team):
        active = add(team, PIA, Discipline.PHYSIO)
        team.end_membership(ADA, active.id, "moved away", T0 + DAY)
        with pytest.raises(InvalidTiming):
            team.end_membership(ADA, active.id, "again", T0 + 2 * DAY)

    def test_unknown_membership(self, team):
        with pytest.raises(NotFound):
            team.end_membership(ADA, uuid4(), "r", T0)


class TestInvariant4Coverage:
    @pytest.fixture
    def pia(self, team):
        return add(team, PIA, Discipline.PHYSIO)

    def cover(self, team, membership, who=SAM, start=T0 + 10 * DAY, days=14, at=T0 + DAY):
        window = TimeRange(start, start + days * DAY)
        return team.schedule_coverage(ADA, membership.id, who, MAYA, window, "Pia on leave", at)

    def test_a_qualified_colleague_covers_for_a_window(self, team, pia):
        coverage = self.cover(team, pia)
        assert coverage.covering_provider_id == SAM.provider_id
        assert coverage.in_effect(T0 + 10 * DAY) and not coverage.in_effect(T0 + 24 * DAY)

    def test_the_cover_must_be_qualified_in_the_covered_discipline(self, team, pia):
        with pytest.raises(NotQualified):
            self.cover(team, pia, who=MIA)  # a massage therapist cannot cover a physio

    def test_a_provider_cannot_cover_themselves(self, team, pia):
        with pytest.raises(InvalidCoverage):
            self.cover(team, pia, who=PIA)

    def test_a_coverage_needs_an_end_and_cannot_start_in_the_past(self, team, pia):
        with pytest.raises(InvalidCoverage):
            team.schedule_coverage(ADA, pia.id, SAM, MAYA, TimeRange(T0 + 10 * DAY), "r", T0 + DAY)
        with pytest.raises(InvalidTiming):
            self.cover(team, pia, start=T0, at=T0 + DAY)

    def test_no_overlapping_coverages_on_one_membership(self, team, pia):
        self.cover(team, pia)
        other_physio = provider(Discipline.PHYSIO)
        with pytest.raises(InvalidCoverage):
            self.cover(team, pia, who=other_physio, start=T0 + 20 * DAY)
        self.cover(team, pia, who=other_physio, start=T0 + 24 * DAY)  # back to back is fine

    def test_handback_ends_a_running_coverage_early(self, team, pia):
        coverage = self.cover(team, pia)
        team.end_coverage(ADA, coverage.id, "Pia is back early", T0 + 17 * DAY)
        (ended,) = team.coverages
        assert ended.window.end == T0 + 17 * DAY
        assert not ended.in_effect(T0 + 17 * DAY)

    def test_ending_a_coverage_that_has_not_started_cancels_it(self, team, pia):
        coverage = self.cover(team, pia)
        team.end_coverage(ADA, coverage.id, "leave cancelled", T0 + 5 * DAY)
        (cancelled,) = team.coverages
        assert cancelled.cancelled_at == T0 + 5 * DAY
        assert not cancelled.in_effect(T0 + 12 * DAY)
        self.cover(team, pia, at=T0 + 5 * DAY)  # the window is free again

    def test_a_finished_coverage_cannot_be_ended(self, team, pia):
        coverage = self.cover(team, pia)
        with pytest.raises(InvalidCoverage):
            team.end_coverage(ADA, coverage.id, "r", T0 + 30 * DAY)

    def test_ending_the_membership_ends_its_running_coverage_and_cancels_later_ones(self, team, pia):
        running = self.cover(team, pia)
        later = self.cover(team, pia, start=T0 + 40 * DAY, days=7)
        team.end_membership(ADA, pia.id, "Maya stopped physio", T0 + 12 * DAY)

        by_id = {c.id: c for c in team.coverages}
        assert by_id[running.id].window.end == T0 + 12 * DAY
        assert by_id[later.id].cancelled_at == T0 + 12 * DAY


class TestInvariant5EveryCommandIsRecorded:
    def test_events_keep_who_what_why_and_when(self, team):
        pia = add(team, PIA, Discipline.PHYSIO)
        consulting = team.change_engagement(ADA, pia.id, Engagement.CONSULTING, "rehab finished", T0 + DAY)
        team.end_membership(ADA, consulting.id, "all done", T0 + 2 * DAY)

        assert [(e.type, e.actor, e.reason, e.at, e.subject_id) for e in team.events] == [
            (TeamEventType.MEMBER_ADDED, ADA, "PHYSIO for Maya", T0, pia.id),
            (TeamEventType.ENGAGEMENT_CHANGED, ADA, "rehab finished", T0 + DAY, consulting.id),
            (TeamEventType.MEMBERSHIP_ENDED, ADA, "all done", T0 + 2 * DAY, consulting.id),
        ]


class TestInvariant7NoSelfTreatment:
    def test_a_client_is_never_a_member_of_their_own_team(self, team):
        maya_as_provider = ProviderFacts(ProviderId(uuid4()), MAYA.person_id, frozenset({Discipline.PHYSIO}))
        with pytest.raises(SelfTreatment):
            add(team, maya_as_provider, Discipline.PHYSIO)

    def test_nor_a_cover_on_it(self, team):
        pia = add(team, PIA, Discipline.PHYSIO)
        maya_as_provider = ProviderFacts(ProviderId(uuid4()), MAYA.person_id, frozenset({Discipline.PHYSIO}))
        with pytest.raises(SelfTreatment):
            team.schedule_coverage(ADA, pia.id, maya_as_provider, MAYA, TimeRange(T0 + DAY, T0 + 2 * DAY), "r", T0)


class TestDischargingAnOrganization:
    def test_every_membership_in_that_org_ends_at_the_same_instant(self, team):
        tom = add(team, TOM, Discipline.TRAINER, GYM)
        gym_physio = provider(Discipline.PHYSIO, GYM)
        add(team, gym_physio, Discipline.PHYSIO, GYM)
        pia = add(team, PIA, Discipline.PHYSIO)
        team.schedule_coverage(ADA, tom.id, provider(Discipline.TRAINER), MAYA, TimeRange(T0 + 5 * DAY, T0 + 9 * DAY), "r", T0)

        team.discharge_organization(ADA, GYM, "Maya left the gym", T0 + 7 * DAY)

        assert [m.provider_id for m in team.memberships_at(T0 + 7 * DAY)] == [pia.provider_id]
        assert {m.period.end for m in team.memberships if m.org_context == GYM} == {T0 + 7 * DAY}
        assert team.coverages[0].window.end == T0 + 7 * DAY
        assert team.events[-1].type is TeamEventType.ORGANIZATION_DISCHARGED

    def test_a_failure_changes_nothing(self, team):
        add(team, TOM, Discipline.TRAINER, GYM)
        late_joiner = provider(Discipline.PHYSIO, GYM)
        add(team, late_joiner, Discipline.PHYSIO, GYM, at=T0 + 5 * DAY)
        with pytest.raises(InvalidTiming):
            team.discharge_organization(ADA, GYM, "r", T0 + 5 * DAY)  # too early for the late joiner
        assert all(m.period.is_open for m in team.memberships)


class TestBriefScenarios:
    def test_trainer_physio_and_physician_at_once_across_orgs(self, team):
        add(team, TOM, Discipline.TRAINER, GYM)
        add(team, PIA, Discipline.PHYSIO)
        add(team, CHEN, Discipline.PHYSICIAN, CLINIC)
        now = team.memberships_at(T0 + DAY)
        assert {(m.discipline, m.org_context) for m in now} == {
            (Discipline.TRAINER, GYM),
            (Discipline.PHYSIO, None),
            (Discipline.PHYSICIAN, CLINIC),
        }
        assert all(m.engagement is Engagement.ACTIVE for m in now)

    def test_history_is_kept_and_the_team_can_be_seen_as_it_was(self, team):
        pia = add(team, PIA, Discipline.PHYSIO)
        team.change_engagement(ADA, pia.id, Engagement.CONSULTING, "rehab finished", T0 + 60 * DAY)

        (before,) = team.memberships_at(T0 + 59 * DAY)
        (after,) = team.memberships_at(T0 + 60 * DAY)
        assert before.engagement is Engagement.ACTIVE
        assert after.engagement is Engagement.CONSULTING
        assert len(team.memberships) == 2  # nothing deleted
