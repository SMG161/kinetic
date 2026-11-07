from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from kinetic.care_team.domain.errors import InvalidReason, InvitationNotForYou, InvitationUnusable, NotQualified
from kinetic.care_team.domain.facts import Discipline, ProviderFacts
from kinetic.care_team.domain.invitations import CareInvitation, hash_invitation_token
from kinetic.shared_kernel import ProviderId, new_person_id

T0 = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
PIA = ProviderFacts(ProviderId(uuid4()), new_person_id(), frozenset({Discipline.PHYSIO}))
MAYA = new_person_id()


@pytest.fixture
def issued() -> tuple[CareInvitation, str]:
    return CareInvitation.issue(PIA, "maya@example.com", Discipline.PHYSIO, "shoulder rehab", T0)


def test_only_the_tokens_hash_is_kept(issued):
    invitation, token = issued
    assert invitation.token_hash == hash_invitation_token(token) != token
    assert invitation.valid.end == T0 + timedelta(days=7)


def test_the_provider_must_be_qualified():
    with pytest.raises(NotQualified):
        CareInvitation.issue(PIA, "maya@example.com", Discipline.PHYSICIAN, "r", T0)


def test_a_reason_is_required():
    with pytest.raises(InvalidReason):
        CareInvitation.issue(PIA, "maya@example.com", Discipline.PHYSIO, " ", T0)


def test_only_the_invited_email_can_accept(issued):
    invitation, _ = issued
    invitation.check_acceptable("maya@example.com", T0 + timedelta(days=1))
    with pytest.raises(InvitationNotForYou):
        invitation.check_acceptable("eve@example.com", T0 + timedelta(days=1))


def test_it_works_once(issued):
    used = issued[0].accept(MAYA, T0 + timedelta(days=1))
    assert used.accepted_by == MAYA
    with pytest.raises(InvitationUnusable, match="used"):
        used.check_acceptable("maya@example.com", T0 + timedelta(days=2))


def test_it_expires_after_a_week(issued):
    with pytest.raises(InvitationUnusable, match="expired"):
        issued[0].check_acceptable("maya@example.com", T0 + timedelta(days=7))
