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
from tests.scenarios.helpers import accept, bearer, invite, login, signup


@pytest.fixture
def people(client: TestClient) -> dict:
    """IronWorks Gym: Olga owns it, Dee is front desk, Ada is admin. Maya is a client."""
    emails = {
        "olga": "olga@ironworks.example",
        "dee": "dee@ironworks.example",
        "ada": "ada@ironworks.example",
        "maya": "maya@example.com",
    }
    headers = {name: bearer(signup(client, f"{name.title()} Person", email)) for name, email in emails.items()}
    ids = {name: client.get("/me", headers=h).json()["id"] for name, h in headers.items()}
    return headers | {"ids": ids, "emails": emails}


@pytest.fixture
def gym(client: TestClient, people: dict) -> dict:
    org = client.post("/orgs", json={"name": "IronWorks Gym"}, headers=people["olga"]).json()
    for name, role in [("dee", "FRONT_DESK"), ("ada", "ADMIN")]:
        token = invite(client, org, people["olga"], kind="STAFF", email=people["emails"][name], role=role)["token"]
        assert accept(client, token, people[name]).status_code == 200
    return org


def serve(client: TestClient, gym: dict, people: dict, inviter: str = "olga", invitee: str = "maya", **overrides) -> object:
    """The gym invites a client and they accept: the only way a relationship starts."""
    body = {
        "kind": "CLIENT",
        "email": people["emails"][invitee],
        "practice_lead_email": "dee@ironworks.example",
        "reason": "Dee coordinates Maya",
    }
    sent = client.post(f"/orgs/{gym['id']}/invitations", json=body | overrides, headers=people[inviter])
    if sent.status_code != 201:
        return sent
    return accept(client, sent.json()["token"], people[invitee])


def relationship(client: TestClient, gym: dict, people: dict, viewer: str = "olga", client_of: str = "maya") -> dict:
    client_id = client.get("/me", headers=people[client_of]).json()["client"]["id"]
    response = client.get(f"/orgs/{gym['id']}/clients/{client_id}", headers=people[viewer])
    assert response.status_code == 200, response.text
    return response.json()


class TestStartingARelationship:
    def test_the_gym_serves_maya_with_a_non_clinical_practice_lead(self, client, people, gym):
        assert serve(client, gym, people).status_code == 200
        lead = relationship(client, gym, people)["practice_lead"]
        assert lead["person_id"] == people["ids"]["dee"]
        assert lead["valid_to"] is None

    def test_only_owner_or_admin_can_invite_a_client(self, client, people, gym):
        assert serve(client, gym, people, inviter="dee").status_code == 403
        assert serve(client, gym, people, inviter="ada").status_code == 200

    def test_one_active_relationship_per_org_and_client(self, client, people, gym):
        serve(client, gym, people)
        assert serve(client, gym, people).status_code == 409

    def test_unknown_practice_lead_email_is_not_found(self, client, people, gym):
        assert serve(client, gym, people, practice_lead_email="nobody@example.com").status_code == 404

    def test_a_client_cannot_be_their_own_practice_lead(self, client, people, gym):
        # Dee works the front desk and is also a client of the gym.
        response = serve(client, gym, people, invitee="dee")
        assert response.status_code == 422
        assert "own practice lead" in response.json()["detail"]


class TestHandingOffTheLead:
    def test_handoff_is_clean_and_history_is_kept(self, client, clock: FixedClock, people, gym):
        serve(client, gym, people)
        maya_client_id = relationship(client, gym, people)["client_id"]
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
        serve(client, gym, people)
        maya_client_id = relationship(client, gym, people)["client_id"]
        clock.advance(timedelta(days=1))
        response = client.post(
            f"/orgs/{gym['id']}/clients/{maya_client_id}/practice-lead",
            json={"practice_lead_email": "ada@ironworks.example", "reason": "taking over"},
            headers=login(client, "dee@ironworks.example"),
        )
        assert response.status_code == 403

    def test_a_reason_is_required(self, client, clock, people, gym):
        serve(client, gym, people)
        maya_client_id = relationship(client, gym, people)["client_id"]
        clock.advance(timedelta(days=1))
        response = client.post(
            f"/orgs/{gym['id']}/clients/{maya_client_id}/practice-lead",
            json={"practice_lead_email": "ada@ironworks.example", "reason": " "},
            headers=login(client, "olga@ironworks.example"),
        )
        assert response.status_code == 422


class TestViewingTheRelationship:
    def test_only_gym_staff_can_see_it(self, client, people, gym):
        serve(client, gym, people)
        maya_client_id = relationship(client, gym, people)["client_id"]
        assert client.get(f"/orgs/{gym['id']}/clients/{maya_client_id}", headers=people["dee"]).status_code == 200
        assert client.get(f"/orgs/{gym['id']}/clients/{maya_client_id}", headers=people["maya"]).status_code == 403


def test_the_database_refuses_two_overlapping_leads(client, people, gym):
    """The safety net for two admins handing off at the same moment: both pass the domain
    check, but Postgres' exclusion constraint rejects the second overlapping period."""
    serve(client, gym, people)
    relationship_id = relationship(client, gym, people)["id"]
    with pytest.raises(IntegrityError, match="one_lead_at_a_time"):
        with db.get_engine().begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO directory.practice_lead_assignment (id, relationship_id, person_id, reason, valid_from)"
                    " VALUES (:id, :rel, :person, 'racing handoff', :at)"
                ),
                {"id": uuid4(), "rel": relationship_id, "person": people["ids"]["ada"], "at": T0 + timedelta(days=1)},
            )
