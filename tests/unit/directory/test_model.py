from datetime import UTC, datetime

import pytest

from kinetic.directory.domain.errors import (
    AlreadyStaff,
    InvalidName,
    InvalidStaffRole,
    NoDisciplines,
    NotAnOrgManager,
    NotQualified,
)
from kinetic.directory.domain.model import Client, Discipline, Organization, Provider, StaffRole
from kinetic.shared_kernel import new_person_id

T0 = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
OWNER = new_person_id()


@pytest.fixture
def gym() -> Organization:
    return Organization.found("IronWorks Gym", OWNER, T0)


def physio_trainer() -> Provider:
    return Provider.register(new_person_id(), [Discipline.PHYSIO, Discipline.TRAINER], T0)


class TestFounding:
    def test_the_founder_becomes_the_owner(self, gym):
        assert gym.roles_of(OWNER) == {StaffRole.OWNER}

    def test_name_is_trimmed_and_required(self):
        assert Organization.found("  IronWorks  ", OWNER, T0).name == "IronWorks"
        with pytest.raises(InvalidName):
            Organization.found("   ", OWNER, T0)


class TestAddingStaff:
    def test_owner_adds_an_admin_who_can_then_add_front_desk(self, gym):
        admin, desk = new_person_id(), new_person_id()
        gym.add_staff(OWNER, admin, StaffRole.ADMIN, T0)
        gym.add_staff(admin, desk, StaffRole.FRONT_DESK, T0)
        assert gym.roles_of(desk) == {StaffRole.FRONT_DESK}

    @pytest.mark.parametrize("actor_role", [StaffRole.FRONT_DESK, None])
    def test_only_owner_or_admin_can_add_staff(self, gym, actor_role):
        actor = new_person_id()
        if actor_role:
            gym.add_staff(OWNER, actor, actor_role, T0)
        with pytest.raises(NotAnOrgManager):
            gym.add_staff(actor, new_person_id(), StaffRole.FRONT_DESK, T0)

    @pytest.mark.parametrize("role", [StaffRole.OWNER, StaffRole.PRACTITIONER])
    def test_cannot_add_a_second_owner_or_a_practitioner_without_disciplines(self, gym, role):
        with pytest.raises(InvalidStaffRole):
            gym.add_staff(OWNER, new_person_id(), role, T0)

    def test_a_person_holds_each_role_once(self, gym):
        admin = new_person_id()
        gym.add_staff(OWNER, admin, StaffRole.ADMIN, T0)
        with pytest.raises(AlreadyStaff):
            gym.add_staff(OWNER, admin, StaffRole.ADMIN, T0)


class TestPractitioners:
    def test_practises_a_subset_of_their_qualifications(self, gym):
        provider = physio_trainer()
        membership = gym.add_practitioner(OWNER, provider, [Discipline.TRAINER], T0)
        assert membership.role == StaffRole.PRACTITIONER
        assert membership.disciplines == {Discipline.TRAINER}

    def test_cannot_practise_what_they_are_not_qualified_in(self, gym):
        with pytest.raises(NotQualified, match="PHYSICIAN"):
            gym.add_practitioner(OWNER, physio_trainer(), [Discipline.PHYSICIAN], T0)

    def test_must_practise_something(self, gym):
        with pytest.raises(NoDisciplines):
            gym.add_practitioner(OWNER, physio_trainer(), [], T0)

    def test_only_owner_or_admin_can_add_practitioners(self, gym):
        with pytest.raises(NotAnOrgManager):
            gym.add_practitioner(new_person_id(), physio_trainer(), [Discipline.TRAINER], T0)

    def test_an_owner_who_also_treats_holds_both_roles(self):
        owner_physio = Provider.register(OWNER, [Discipline.PHYSIO], T0)
        clinic = Organization.found("Knee Clinic", OWNER, T0)
        clinic.add_practitioner(OWNER, owner_physio, [Discipline.PHYSIO], T0)
        assert clinic.roles_of(OWNER) == {StaffRole.OWNER, StaffRole.PRACTITIONER}


class TestProfiles:
    def test_a_provider_needs_a_discipline(self):
        with pytest.raises(NoDisciplines):
            Provider.register(new_person_id(), [], T0)

    def test_one_person_can_be_client_and_provider(self):
        person = new_person_id()
        client = Client.register(person, T0)
        provider = Provider.register(person, [Discipline.TRAINER], T0)
        assert client.person_id == provider.person_id == person
        assert client.id != provider.id
