"""Brief, build target 1: the system knows what people are (client, provider, org staff),
and one person may hold several of these at once. Invitations are the only way into an org."""

import pytest
from fastapi.testclient import TestClient

from tests.scenarios.helpers import PASSWORD, accept, bearer, invite, signup


@pytest.fixture
def owner(client: TestClient) -> dict:
    return bearer(signup(client, "Olga Owner", "olga@ironworks.example"))


@pytest.fixture
def gym(client: TestClient, owner: dict) -> dict:
    response = client.post("/orgs", json={"name": "IronWorks Gym"}, headers=owner)
    assert response.status_code == 201, response.text
    return response.json()


def me(client: TestClient, headers: dict) -> dict:
    response = client.get("/me", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def signup_provider(client: TestClient, full_name: str, email: str, qualifications: list[str]) -> object:
    body = {"full_name": full_name, "email": email, "password": PASSWORD, "qualifications": qualifications}
    return client.post("/auth/signup", json=body)


class TestPersonas:
    def test_signup_makes_you_a_client_and_nothing_else(self, client):
        maya = bearer(signup(client, "Maya Patel", "maya@example.com"))
        profile = me(client, maya)
        assert profile["client"] is not None
        assert profile["provider"] is None
        assert profile["staff"] == []

    def test_signing_up_as_a_provider_makes_you_a_provider_not_a_client(self, client):
        response = signup_provider(client, "Sam Cover", "sam@example.com", ["PHYSIO"])
        assert response.status_code == 201, response.text
        profile = me(client, bearer(response.json()))
        assert profile["provider"]["qualifications"] == ["PHYSIO"]
        assert profile["client"] is None

    def test_provider_signup_with_an_unknown_discipline_leaves_nothing_behind(self, client):
        assert signup_provider(client, "Sam Cover", "sam@example.com", ["WIZARD"]).status_code == 422
        assert signup_provider(client, "Sam Cover", "sam@example.com", ["PHYSIO"]).status_code == 201

    def test_a_provider_becomes_a_client_by_accepting_a_client_invitation(self, client, owner, gym):
        sam = bearer(signup_provider(client, "Sam Cover", "sam@example.com", ["PHYSIO"]).json())
        token = invite(
            client, gym, owner, kind="CLIENT", email="sam@example.com",
            practice_lead_email="olga@ironworks.example", reason="Sam trains here too",
        )["token"]
        assert accept(client, token, sam).status_code == 200
        profile = me(client, sam)
        assert profile["client"] is not None
        assert profile["provider"]["qualifications"] == ["PHYSIO"]

    def test_a_client_can_also_be_a_provider(self, client):
        tom = bearer(signup(client, "Tom Trainer", "tom@example.com"))
        response = client.post("/providers", json={"qualifications": ["TRAINER"]}, headers=tom)
        assert response.status_code == 201
        profile = me(client, tom)
        assert profile["client"] is not None
        assert profile["provider"]["qualifications"] == ["TRAINER"]

    def test_one_provider_profile_per_person(self, client):
        tom = bearer(signup(client, "Tom Trainer", "tom@example.com"))
        client.post("/providers", json={"qualifications": ["TRAINER"]}, headers=tom)
        assert client.post("/providers", json={"qualifications": ["PHYSIO"]}, headers=tom).status_code == 409

    def test_unknown_discipline_is_rejected(self, client):
        tom = bearer(signup(client, "Tom Trainer", "tom@example.com"))
        assert client.post("/providers", json={"qualifications": ["WIZARD"]}, headers=tom).status_code == 422


class TestOrganizations:
    def test_founding_an_org_makes_you_its_owner(self, client, owner, gym):
        assert [p["role"] for p in me(client, owner)["staff"]] == ["OWNER"]
        assert me(client, owner)["staff"][0]["organization_name"] == "IronWorks Gym"

    def test_founding_requires_sign_in(self, client):
        assert client.post("/orgs", json={"name": "IronWorks Gym"}).status_code == 401

    def test_nobody_can_be_added_without_accepting_an_invitation(self, client, owner, gym):
        signup(client, "Ada Admin", "ada@ironworks.example")
        staff = client.post(f"/orgs/{gym['id']}/staff", json={"email": "ada@ironworks.example", "role": "ADMIN"}, headers=owner)
        clients = client.post(f"/orgs/{gym['id']}/clients", json={"client_email": "ada@ironworks.example"}, headers=owner)
        assert staff.status_code == clients.status_code == 404  # no such routes

    def test_owner_invites_admin_who_invites_front_desk(self, client, owner, gym):
        ada = bearer(signup(client, "Ada Admin", "ada@ironworks.example"))
        dee = bearer(signup(client, "Dee Desk", "dee@ironworks.example"))
        assert accept(client, invite(client, gym, owner, kind="STAFF", email="ada@ironworks.example", role="ADMIN")["token"], ada).status_code == 200
        assert accept(client, invite(client, gym, ada, kind="STAFF", email="dee@ironworks.example", role="FRONT_DESK")["token"], dee).status_code == 200
        assert [p["role"] for p in me(client, dee)["staff"]] == ["FRONT_DESK"]

    def test_outsiders_cannot_invite_or_probe_emails(self, client, gym):
        outsider = bearer(signup(client, "Eve Outsider", "eve@example.com"))

        def invite_client_led_by(lead_email: str) -> int:
            body = {"kind": "CLIENT", "email": "maya@example.com", "practice_lead_email": lead_email, "reason": "r"}
            return client.post(f"/orgs/{gym['id']}/invitations", json=body, headers=outsider).status_code

        assert invite_client_led_by("olga@ironworks.example") == invite_client_led_by("nobody@example.com") == 403

    def test_cannot_invite_a_second_owner(self, client, owner, gym):
        body = {"kind": "STAFF", "email": "ada@ironworks.example", "role": "OWNER"}
        assert client.post(f"/orgs/{gym['id']}/invitations", json=body, headers=owner).status_code == 422

    def test_same_role_twice_conflicts(self, client, owner, gym):
        ada = bearer(signup(client, "Ada Admin", "ada@ironworks.example"))
        first = invite(client, gym, owner, kind="STAFF", email="ada@ironworks.example", role="ADMIN")["token"]
        second = invite(client, gym, owner, kind="STAFF", email="ada@ironworks.example", role="ADMIN")["token"]
        assert accept(client, first, ada).status_code == 200
        assert accept(client, second, ada).status_code == 409

    def test_unknown_org_is_not_found(self, client, owner):
        body = {"kind": "STAFF", "email": "ada@ironworks.example", "role": "ADMIN"}
        ghost = "00000000-0000-0000-0000-000000000000"
        assert client.post(f"/orgs/{ghost}/invitations", json=body, headers=owner).status_code == 404


class TestPractitioners:
    def test_a_practitioner_practises_disciplines_they_are_qualified_in(self, client, owner, gym):
        pia = bearer(signup_provider(client, "Pia Physio", "pia@example.com", ["PHYSIO", "TRAINER"]).json())
        token = invite(client, gym, owner, kind="PRACTITIONER", email="pia@example.com", disciplines=["TRAINER"])["token"]
        assert accept(client, token, pia).status_code == 200
        assert me(client, pia)["staff"] == [
            {
                "organization_id": gym["id"],
                "organization_name": "IronWorks Gym",
                "role": "PRACTITIONER",
                "disciplines": ["TRAINER"],
            }
        ]

    def test_a_clinic_owner_who_also_treats_invites_themselves(self, client, owner, gym):
        client.post("/providers", json={"qualifications": ["PHYSIO"]}, headers=owner)
        token = invite(client, gym, owner, kind="PRACTITIONER", email="olga@ironworks.example", disciplines=["PHYSIO"])["token"]
        assert accept(client, token, owner).status_code == 200
        assert sorted(p["role"] for p in me(client, owner)["staff"]) == ["OWNER", "PRACTITIONER"]
