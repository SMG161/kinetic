from datetime import UTC, datetime, timedelta

import pytest

from kinetic.directory.domain.errors import InvalidPracticeLead, InvalidReason, NotAnOrgManager
from kinetic.directory.domain.model import Client, Organization, StaffRole
from kinetic.directory.domain.relationships import ClientRelationship
from kinetic.shared_kernel import new_person_id

T0 = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
LATER = T0 + timedelta(days=7)
OWNER, DESK, ADMIN = new_person_id(), new_person_id(), new_person_id()


@pytest.fixture
def gym() -> Organization:
    org = Organization.found("IronWorks Gym", OWNER, T0)
    org.add_staff(OWNER, DESK, StaffRole.FRONT_DESK, T0)
    org.add_staff(OWNER, ADMIN, StaffRole.ADMIN, T0)
    return org


@pytest.fixture
def maya() -> Client:
    return Client.register(new_person_id(), T0)


@pytest.fixture
def served(gym, maya) -> ClientRelationship:
    return ClientRelationship.start(gym, OWNER, maya, DESK, "front desk coordinates Maya", T0)


class TestStart:
    def test_a_non_clinical_staff_member_can_be_the_practice_lead(self, served):
        assert served.current_lead.person_id == DESK
        assert served.period.is_open

    def test_only_owner_or_admin_can_start_one(self, gym, maya):
        with pytest.raises(NotAnOrgManager):
            ClientRelationship.start(gym, DESK, maya, DESK, "reason", T0)

    def test_the_lead_must_be_staff(self, gym, maya):
        with pytest.raises(InvalidPracticeLead, match="staff"):
            ClientRelationship.start(gym, OWNER, maya, new_person_id(), "reason", T0)

    def test_a_client_cannot_be_their_own_practice_lead(self, gym):
        trainer_client = new_person_id()
        gym.add_staff(OWNER, trainer_client, StaffRole.FRONT_DESK, T0)
        with pytest.raises(InvalidPracticeLead, match="own"):
            ClientRelationship.start(gym, OWNER, Client.register(trainer_client, T0), trainer_client, "reason", T0)

    def test_a_reason_is_required(self, gym, maya):
        with pytest.raises(InvalidReason):
            ClientRelationship.start(gym, OWNER, maya, DESK, "   ", T0)


class TestHandoff:
    def test_closes_the_old_lead_and_opens_the_new_at_the_same_instant(self, served, gym, maya):
        served.hand_off_lead(gym, OWNER, maya, ADMIN, "Dee is on leave", LATER)
        old, new = served.leads
        assert old.period.end == new.period.start == LATER
        assert served.current_lead.person_id == ADMIN

    def test_exactly_one_lead_at_every_instant(self, served, gym, maya):
        served.hand_off_lead(gym, OWNER, maya, ADMIN, "Dee is on leave", LATER)
        assert served.lead_at(LATER - timedelta(microseconds=1)) == DESK
        assert served.lead_at(LATER) == ADMIN
        assert served.lead_at(T0 - timedelta(seconds=1)) is None

    def test_history_keeps_every_lead_and_reason(self, served, gym, maya):
        served.hand_off_lead(gym, OWNER, maya, ADMIN, "Dee is on leave", LATER)
        assert [(a.person_id, a.reason) for a in served.leads] == [
            (DESK, "front desk coordinates Maya"),
            (ADMIN, "Dee is on leave"),
        ]

    def test_only_owner_or_admin_can_hand_off(self, served, gym, maya):
        with pytest.raises(NotAnOrgManager):
            served.hand_off_lead(gym, DESK, maya, ADMIN, "reason", LATER)

    def test_handing_off_to_the_current_lead_is_rejected(self, served, gym, maya):
        with pytest.raises(InvalidPracticeLead, match="already"):
            served.hand_off_lead(gym, OWNER, maya, DESK, "reason", LATER)

    def test_a_rejected_handoff_changes_nothing(self, served, gym, maya):
        with pytest.raises(InvalidPracticeLead):
            served.hand_off_lead(gym, OWNER, maya, new_person_id(), "not staff", LATER)
        assert len(served.leads) == 1
        assert served.current_lead.person_id == DESK

    def test_cannot_hand_off_at_or_before_the_current_lead_started(self, served, gym, maya):
        with pytest.raises(InvalidPracticeLead, match="after"):
            served.hand_off_lead(gym, OWNER, maya, ADMIN, "reason", T0)
