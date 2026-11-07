"""Brief, build target 1: onboarding and invitations. An org brings people in as staff,
practitioners or clients; accepting is the invitee's consent."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from kinetic.shared_kernel import FixedClock
from tests.scenarios.helpers import PASSWORD, bearer, invite, login, signup


@pytest.fixture
def owner(client: TestClient) -> dict:
    return bearer(signup(client, "Olga Owner", "olga@ironworks.example"))


@pytest.fixture
def gym(client: TestClient, owner: dict) -> dict:
    return client.post("/orgs", json={"name": "IronWorks Gym"}, headers=owner).json()


def accept_as_new(client: TestClient, token: str, name: str = "New Person", password: str = PASSWORD) -> object:
    return client.post("/invitations/accept", json={"token": token, "full_name": name, "password": password})


def me(client: TestClient, headers: dict) -> dict:
    return client.get("/me", headers=headers).json()


class TestStaffInvitations:
    def test_a_new_person_accepts_and_is_signed_in_as_front_desk(self, client, owner, gym):
        token = invite(client, gym, owner, kind="STAFF", email="Dee@IronWorks.example", role="FRONT_DESK")["token"]
        response = accept_as_new(client, token, "Dee Desk")
        assert response.status_code == 200, response.text

        dee = bearer(response.json()["tokens"])
        profile = me(client, dee)
        assert profile["email"] == "dee@ironworks.example"
        assert [s["role"] for s in profile["staff"]] == ["FRONT_DESK"]
        assert profile["client"] is None  # invited staff are not automatically clients

    def test_someone_with_an_account_accepts_while_signed_in(self, client, owner, gym):
        ada = bearer(signup(client, "Ada Admin", "ada@ironworks.example"))
        token = invite(client, gym, owner, kind="STAFF", email="ada@ironworks.example", role="ADMIN")["token"]
        response = client.post("/invitations/accept", json={"token": token}, headers=ada)
        assert response.status_code == 200
        assert response.json()["tokens"] is None
        assert [s["role"] for s in me(client, ada)["staff"]] == ["ADMIN"]

    def test_only_the_invited_email_can_accept(self, client, owner, gym):
        eve = bearer(signup(client, "Eve Elsewhere", "eve@example.com"))
        token = invite(client, gym, owner, kind="STAFF", email="ada@ironworks.example", role="ADMIN")["token"]
        assert client.post("/invitations/accept", json={"token": token}, headers=eve).status_code == 403

    def test_an_existing_email_must_sign_in_instead_of_creating_an_account(self, client, owner, gym):
        signup(client, "Ada Admin", "ada@ironworks.example")
        token = invite(client, gym, owner, kind="STAFF", email="ada@ironworks.example", role="ADMIN")["token"]
        assert accept_as_new(client, token).status_code == 409

    def test_only_owner_or_admin_can_invite(self, client, owner, gym):
        token = invite(client, gym, owner, kind="STAFF", email="dee@ironworks.example", role="FRONT_DESK")["token"]
        dee = bearer(accept_as_new(client, token).json()["tokens"])
        response = client.post(
            f"/orgs/{gym['id']}/invitations", json={"kind": "STAFF", "email": "x@example.com", "role": "ADMIN"}, headers=dee
        )
        assert response.status_code == 403


class TestTokens:
    def test_works_once(self, client, owner, gym):
        token = invite(client, gym, owner, kind="STAFF", email="dee@ironworks.example", role="FRONT_DESK")["token"]
        assert accept_as_new(client, token).status_code == 200
        assert accept_as_new(client, token).status_code == 410

    def test_expires_after_a_week(self, client, clock: FixedClock, owner, gym):
        token = invite(client, gym, owner, kind="STAFF", email="dee@ironworks.example", role="FRONT_DESK")["token"]
        clock.advance(timedelta(days=7))
        assert accept_as_new(client, token).status_code == 410

    def test_unknown_token(self, client):
        assert accept_as_new(client, "not-a-real-token").status_code == 404

    def test_a_forged_bearer_token_is_rejected_not_treated_as_anonymous(self, client, owner, gym):
        token = invite(client, gym, owner, kind="STAFF", email="dee@ironworks.example", role="FRONT_DESK")["token"]
        response = client.post("/invitations/accept", json={"token": token}, headers={"Authorization": "Bearer forged"})
        assert response.status_code == 401

    def test_a_failed_acceptance_changes_nothing_and_can_be_retried(self, client, owner, gym):
        token = invite(client, gym, owner, kind="STAFF", email="dee@ironworks.example", role="FRONT_DESK")["token"]
        assert accept_as_new(client, token, password="short").status_code == 422  # weak password
        assert accept_as_new(client, token).status_code == 200  # still pending, email still free

    def test_a_new_person_must_give_name_and_password(self, client, owner, gym):
        token = invite(client, gym, owner, kind="STAFF", email="dee@ironworks.example", role="FRONT_DESK")["token"]
        assert client.post("/invitations/accept", json={"token": token}).status_code == 422


class TestPractitionerInvitations:
    def test_a_new_practitioner_gets_a_provider_profile_and_a_membership(self, client, owner, gym):
        token = invite(client, gym, owner, kind="PRACTITIONER", email="tom@example.com", disciplines=["TRAINER"])["token"]
        tom = bearer(accept_as_new(client, token, "Tom Trainer").json()["tokens"])
        profile = me(client, tom)
        assert profile["provider"]["qualifications"] == ["TRAINER"]
        assert profile["staff"][0] | {"organization_id": None} == {
            "organization_id": None,
            "organization_name": "IronWorks Gym",
            "role": "PRACTITIONER",
            "disciplines": ["TRAINER"],
        }

    def test_an_existing_provider_must_be_qualified(self, client, owner, gym):
        pia = bearer(signup(client, "Pia Physio", "pia@example.com"))
        client.post("/providers", json={"qualifications": ["PHYSIO"]}, headers=pia)
        token = invite(client, gym, owner, kind="PRACTITIONER", email="pia@example.com", disciplines=["PHYSICIAN"])["token"]
        assert client.post("/invitations/accept", json={"token": token}, headers=pia).status_code == 422


class TestClientInvitations:
    def test_accepting_is_the_clients_consent_to_be_served(self, client, owner, gym):
        token = invite(
            client,
            gym,
            owner,
            kind="CLIENT",
            email="maya@example.com",
            practice_lead_email="olga@ironworks.example",
            reason="Olga coordinates new members",
        )["token"]
        maya = bearer(accept_as_new(client, token, "Maya Patel").json()["tokens"])
        maya_client_id = me(client, maya)["client"]["id"]

        relationship = client.get(f"/orgs/{gym['id']}/clients/{maya_client_id}", headers=login(client, "olga@ironworks.example"))
        assert relationship.status_code == 200
        assert relationship.json()["practice_lead"]["reason"] == "Olga coordinates new members"

    def test_the_practice_lead_must_be_staff(self, client, owner, gym):
        signup(client, "Sam Someone", "sam@example.com")
        response = client.post(
            f"/orgs/{gym['id']}/invitations",
            json={"kind": "CLIENT", "email": "maya@example.com", "practice_lead_email": "sam@example.com", "reason": "r"},
            headers=owner,
        )
        assert response.status_code == 422

    def test_fields_from_another_kind_are_rejected(self, client, owner, gym):
        response = client.post(
            f"/orgs/{gym['id']}/invitations",
            json={"kind": "CLIENT", "email": "maya@example.com", "role": "ADMIN"},
            headers=owner,
        )
        assert response.status_code == 422
