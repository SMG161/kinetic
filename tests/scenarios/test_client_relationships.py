"""Cross-organization: a client belongs to an org even when none of its providers treats her,
and each org has one accountable practice lead for her at every instant, with history kept."""

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from kinetic import db
from kinetic.shared_kernel import FixedClock
from tests.scenarios.conftest import T0
from tests.scenarios.helpers import bearer, login, signup


@pytest.fixture
def people(client: TestClient) -> dict:
    """IronWorks Gym: Olga owns it, Dee is front desk, Ada is admin. Maya is a client."""
    headers = {
        "olga": bearer(signup(client, "Olga Owner", "olga@ironworks.example")),
        "dee": bearer(signup(client, "Dee Desk", "dee@ironworks.example")),
        "ada": bearer(signup(client, "Ada Admin", "ada@ironworks.example")),
        "maya": bearer(signup(client, "Maya Patel", "maya@example.com")),
    }
    ids = {name: client.get("/me", headers=h).json()["id"] for name, h in headers.items()}
    return headers | {"ids": ids}


@pytest.fixture
def gym(client: TestClient, people: dict) -> dict:
    org = client.post("/orgs", json={"name": "IronWorks Gym"}, headers=people["olga"]).json()
    for email, role in [("dee@ironworks.example", "FRONT_DESK"), ("ada@ironworks.example", "ADMIN")]:
        response = client.post(f"/orgs/{org['id']}/staff", json={"email": email, "role": role}, headers=people["olga"])
        assert response.status_code == 201, response.text
    return org


def start(client: TestClient, gym: dict, headers: dict, **overrides) -> object:
    body = {"client_email": "maya@example.com", "practice_lead_email": "dee@ironworks.example", "reason": "Dee coordinates Maya"}
    return client.post(f"/orgs/{gym['id']}/clients", json=body | overrides, headers=headers)


class TestStartingARelationship:
    def test_the_gym_serves_maya_with_a_non_clinical_practice_lead(self, client, people, gym):
        response = start(client, gym, people["olga"])
        assert response.status_code == 201, response.text
        lead = response.json()["practice_lead"]
        assert lead["person_id"] == people["ids"]["dee"]
        assert lead["valid_to"] is None

    def test_only_owner_or_admin_can_start_one(self, client, people, gym):
        assert start(client, gym, people["dee"]).status_code == 403
        assert start(client, gym, people["ada"]).status_code == 201

    def test_one_active_relationship_per_org_and_client(self, client, people, gym):
        start(client, gym, people["olga"])
        assert start(client, gym, people["olga"]).status_code == 409

    def test_the_lead_must_be_gym_staff(self, client, people, gym):
        signup(client, "Sam Someone", "sam@example.com")
        assert start(client, gym, people["olga"], practice_lead_email="sam@example.com").status_code == 422

    def test_unknown_client_email_is_not_found(self, client, people, gym):
        assert start(client, gym, people["olga"], client_email="nobody@example.com").status_code == 404

    def test_a_client_cannot_be_their_own_practice_lead(self, client, people, gym):
        # Dee works the front desk and is also a client of the gym.
        response = start(client, gym, people["olga"], client_email="dee@ironworks.example")
        assert response.status_code == 422
        assert "own practice lead" in response.json()["detail"]


class TestHandingOffTheLead:
    def test_handoff_is_clean_and_history_is_kept(self, client, clock: FixedClock, people, gym):
        maya_client_id = start(client, gym, people["olga"]).json()["client_id"]
        clock.advance(timedelta(days=7))  # a week later, so everyone signs in again
        response = client.post(
            f"/orgs/{gym['id']}/clients/{maya_client_id}/practice-lead",
            json={"practice_lead_email": "ada@ironworks.example", "reason": "Dee is on leave"},
            headers=login(client, "ada@ironworks.example"),
        )
        assert response.status_code == 200, response.text

        dee = login(client, "dee@ironworks.example")
        history = client.get(f"/orgs/{gym['id']}/clients/{maya_client_id}", headers=dee).json()["lead_history"]
        assert [(h["person_id"], h["reason"]) for h in history] == [
            (people["ids"]["dee"], "Dee coordinates Maya"),
            (people["ids"]["ada"], "Dee is on leave"),
        ]
        # No gap, no overlap: the old period ends exactly when the new one starts.
        assert history[0]["valid_to"] == history[1]["valid_from"]
        assert history[1]["valid_to"] is None

    def test_front_desk_cannot_hand_off(self, client, clock, people, gym):
        maya_client_id = start(client, gym, people["olga"]).json()["client_id"]
        clock.advance(timedelta(days=1))
        response = client.post(
            f"/orgs/{gym['id']}/clients/{maya_client_id}/practice-lead",
            json={"practice_lead_email": "ada@ironworks.example", "reason": "taking over"},
            headers=login(client, "dee@ironworks.example"),
        )
        assert response.status_code == 403

    def test_a_reason_is_required(self, client, clock, people, gym):
        maya_client_id = start(client, gym, people["olga"]).json()["client_id"]
        clock.advance(timedelta(days=1))
        response = client.post(
            f"/orgs/{gym['id']}/clients/{maya_client_id}/practice-lead",
            json={"practice_lead_email": "ada@ironworks.example", "reason": " "},
            headers=login(client, "olga@ironworks.example"),
        )
        assert response.status_code == 422


class TestViewingTheRelationship:
    def test_only_gym_staff_can_see_it(self, client, people, gym):
        maya_client_id = start(client, gym, people["olga"]).json()["client_id"]
        assert client.get(f"/orgs/{gym['id']}/clients/{maya_client_id}", headers=people["dee"]).status_code == 200
        assert client.get(f"/orgs/{gym['id']}/clients/{maya_client_id}", headers=people["maya"]).status_code == 403


def test_the_database_refuses_two_overlapping_leads(client, people, gym):
    """The safety net for two admins handing off at the same moment: both pass the domain
    check, but Postgres' exclusion constraint rejects the second overlapping period."""
    relationship_id = start(client, gym, people["olga"]).json()["id"]
    with pytest.raises(IntegrityError, match="one_lead_at_a_time"):
        with db.get_engine().begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO directory.practice_lead_assignment (id, relationship_id, person_id, reason, valid_from)"
                    " VALUES (:id, :rel, :person, 'racing handoff', :at)"
                ),
                {"id": uuid4(), "rel": relationship_id, "person": people["ids"]["ada"], "at": T0 + timedelta(days=1)},
            )
