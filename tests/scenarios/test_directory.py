"""Brief, build target 1: the system knows what people are (client, provider, org staff),
and one person may hold several of these at once."""

import pytest
from fastapi.testclient import TestClient

from tests.scenarios.helpers import bearer, signup


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


def add_staff(client: TestClient, org: dict, headers: dict, **body) -> object:
    return client.post(f"/orgs/{org['id']}/staff", json=body, headers=headers)


class TestPersonas:
    def test_signup_makes_you_a_client_and_nothing_else(self, client):
        maya = bearer(signup(client, "Maya Patel", "maya@example.com"))
        profile = me(client, maya)
        assert profile["client"] is not None
        assert profile["provider"] is None
        assert profile["staff"] == []

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

    def test_owner_adds_admin_who_adds_front_desk_who_cannot_add_anyone(self, client, owner, gym):
        admin = bearer(signup(client, "Ada Admin", "ada@ironworks.example"))
        desk = bearer(signup(client, "Dee Desk", "dee@ironworks.example"))
        signup(client, "Sam Someone", "sam@example.com")

        assert add_staff(client, gym, owner, email="ada@ironworks.example", role="ADMIN").status_code == 201
        assert add_staff(client, gym, admin, email="dee@ironworks.example", role="FRONT_DESK").status_code == 201
        assert add_staff(client, gym, desk, email="sam@example.com", role="FRONT_DESK").status_code == 403

    def test_outsiders_cannot_add_staff_or_probe_emails(self, client, gym):
        outsider = bearer(signup(client, "Eve Outsider", "eve@example.com"))
        known = add_staff(client, gym, outsider, email="olga@ironworks.example", role="ADMIN")
        unknown = add_staff(client, gym, outsider, email="nobody@example.com", role="ADMIN")
        assert known.status_code == unknown.status_code == 403

    def test_cannot_add_a_second_owner(self, client, owner, gym):
        signup(client, "Ada Admin", "ada@ironworks.example")
        assert add_staff(client, gym, owner, email="ada@ironworks.example", role="OWNER").status_code == 422

    def test_same_role_twice_conflicts(self, client, owner, gym):
        signup(client, "Ada Admin", "ada@ironworks.example")
        add_staff(client, gym, owner, email="ada@ironworks.example", role="ADMIN")
        assert add_staff(client, gym, owner, email="ada@ironworks.example", role="ADMIN").status_code == 409

    def test_unknown_email_and_unknown_org_are_not_found(self, client, owner, gym):
        assert add_staff(client, gym, owner, email="nobody@example.com", role="ADMIN").status_code == 404
        ghost = {"id": "00000000-0000-0000-0000-000000000000"}
        assert add_staff(client, ghost, owner, email="olga@ironworks.example", role="ADMIN").status_code == 404


class TestPractitioners:
    def test_a_practitioner_practises_disciplines_they_are_qualified_in(self, client, owner, gym):
        pia = bearer(signup(client, "Pia Physio", "pia@example.com"))
        client.post("/providers", json={"qualifications": ["PHYSIO", "TRAINER"]}, headers=pia)

        response = add_staff(client, gym, owner, email="pia@example.com", role="PRACTITIONER", disciplines=["TRAINER"])
        assert response.status_code == 201
        assert me(client, pia)["staff"] == [
            {
                "organization_id": gym["id"],
                "organization_name": "IronWorks Gym",
                "role": "PRACTITIONER",
                "disciplines": ["TRAINER"],
            }
        ]

    def test_cannot_practise_without_the_qualification(self, client, owner, gym):
        pia = bearer(signup(client, "Pia Physio", "pia@example.com"))
        client.post("/providers", json={"qualifications": ["PHYSIO"]}, headers=pia)
        response = add_staff(client, gym, owner, email="pia@example.com", role="PRACTITIONER", disciplines=["PHYSICIAN"])
        assert response.status_code == 422

    def test_a_practitioner_needs_a_provider_profile(self, client, owner, gym):
        signup(client, "Sam Someone", "sam@example.com")
        response = add_staff(client, gym, owner, email="sam@example.com", role="PRACTITIONER", disciplines=["TRAINER"])
        assert response.status_code == 404

    def test_only_practitioners_have_disciplines(self, client, owner, gym):
        signup(client, "Dee Desk", "dee@ironworks.example")
        response = add_staff(client, gym, owner, email="dee@ironworks.example", role="FRONT_DESK", disciplines=["TRAINER"])
        assert response.status_code == 422

    def test_a_clinic_owner_who_also_treats(self, client, owner, gym):
        client.post("/providers", json={"qualifications": ["PHYSIO"]}, headers=owner)
        response = add_staff(client, gym, owner, email="olga@ironworks.example", role="PRACTITIONER", disciplines=["PHYSIO"])
        assert response.status_code == 201
        assert sorted(p["role"] for p in me(client, owner)["staff"]) == ["OWNER", "PRACTITIONER"]
