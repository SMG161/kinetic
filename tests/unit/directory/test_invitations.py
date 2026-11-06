from datetime import UTC, datetime, timedelta

import pytest

from kinetic.directory.domain.errors import (
    InvalidPracticeLead,
    InvalidReason,
    InvalidStaffRole,
    InvitationNotForYou,
    InvitationUnusable,
    NoDisciplines,
    NotAnOrgManager,
)
from kinetic.directory.domain.invitations import INVITATION_LIFETIME, Invitation, InvitationKind, hash_invitation_token
from kinetic.directory.domain.model import Discipline, Organization, StaffRole
from kinetic.shared_kernel import new_person_id

T0 = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
OWNER, DESK = new_person_id(), new_person_id()
EMAIL = "new@example.com"


@pytest.fixture
def gym() -> Organization:
    org = Organization.found("IronWorks Gym", OWNER, T0)
    org.add_staff(OWNER, DESK, StaffRole.FRONT_DESK, T0)
    return org


class TestIssuing:
    def test_only_the_hash_of_the_token_is_kept(self, gym):
        invitation, token = Invitation.for_staff(gym, OWNER, EMAIL, StaffRole.FRONT_DESK, T0)
        assert invitation.token_hash == hash_invitation_token(token)
        assert token not in invitation.token_hash

    def test_expires_after_a_week(self, gym):
        invitation, _ = Invitation.for_staff(gym, OWNER, EMAIL, StaffRole.ADMIN, T0)
        assert invitation.valid.end == T0 + INVITATION_LIFETIME

    def test_only_owner_or_admin_can_invite(self, gym):
        with pytest.raises(NotAnOrgManager):
            Invitation.for_staff(gym, DESK, EMAIL, StaffRole.FRONT_DESK, T0)
        with pytest.raises(NotAnOrgManager):
            Invitation.for_practitioner(gym, DESK, EMAIL, [Discipline.TRAINER], T0)
        with pytest.raises(NotAnOrgManager):
            Invitation.for_client(gym, DESK, EMAIL, DESK, "reason", T0)

    @pytest.mark.parametrize("role", [StaffRole.OWNER, StaffRole.PRACTITIONER])
    def test_staff_invitations_are_for_admin_or_front_desk(self, gym, role):
        with pytest.raises(InvalidStaffRole):
            Invitation.for_staff(gym, OWNER, EMAIL, role, T0)

    def test_practitioner_invitations_need_a_discipline(self, gym):
        with pytest.raises(NoDisciplines):
            Invitation.for_practitioner(gym, OWNER, EMAIL, [], T0)

    def test_client_invitations_name_a_staff_lead_and_a_reason(self, gym):
        invitation, _ = Invitation.for_client(gym, OWNER, EMAIL, DESK, "Dee coordinates", T0)
        assert (invitation.kind, invitation.practice_lead) == (InvitationKind.CLIENT, DESK)
        with pytest.raises(InvalidPracticeLead):
            Invitation.for_client(gym, OWNER, EMAIL, new_person_id(), "reason", T0)
        with pytest.raises(InvalidReason):
            Invitation.for_client(gym, OWNER, EMAIL, DESK, "  ", T0)


class TestAccepting:
    @pytest.fixture
    def invitation(self, gym) -> Invitation:
        return Invitation.for_staff(gym, OWNER, EMAIL, StaffRole.FRONT_DESK, T0)[0]

    def test_acceptable_by_the_invited_email_within_the_week(self, invitation):
        invitation.check_acceptable(EMAIL, T0 + INVITATION_LIFETIME - timedelta(seconds=1))

    def test_expired_from_the_end_of_the_week(self, invitation):
        with pytest.raises(InvitationUnusable, match="expired"):
            invitation.check_acceptable(EMAIL, T0 + INVITATION_LIFETIME)

    def test_works_once(self, invitation):
        used = invitation.accept(new_person_id(), T0)
        with pytest.raises(InvitationUnusable, match="used"):
            used.check_acceptable(EMAIL, T0)

    def test_not_for_someone_with_another_email(self, invitation):
        with pytest.raises(InvitationNotForYou):
            invitation.check_acceptable("someone.else@example.com", T0)
