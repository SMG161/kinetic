"""Brief, cross-organization: the client belongs to a gym but also sees an independent
physiotherapist who is not the gym's staff. Pia joins Maya's team by care invitation,
and Maya accepting is her consent."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from kinetic.shared_kernel import FixedClock
from tests.scenarios.helpers import PASSWORD, accept, bearer, invite, login, signup

DAY = timedelta(days=1)
ADA, MAYA, PIA, TOM = "ada@ironworks.example", "maya@example.com", "pia@example.com", "tom@ironworks.example"


def signup_provider(client: TestClient, name: str, email: str, discipline: str) -> dict:
    body = {"full_name": name, "email": email, "password": PASSWORD, "qualifications": [discipline]}
    return bearer(client.post("/auth/signup", json=body).json())


@pytest.fixture
def world(client: TestClient) -> dict:
    """IronWorks serves Maya (Ada leads her there; Tom is on her team). Pia is a solo physio."""
    olga = bearer(signup(client, "Olga Owner", "olga@ironworks.example"))
    gym = client.post("/orgs", json={"name": "IronWorks Gym"}, headers=olga).json()
    ada = bearer(signup(client, "Ada Admin", ADA))
    accept(client, invite(client, gym, olga, kind="STAFF", email=ADA, role="ADMIN")["token"], ada)
    token = invite(client, gym, olga, kind="PRACTITIONER", email=TOM, disciplines=["TRAINER"])["token"]
    client.post("/invitations/accept", json={"token": token, "full_name": "Tom", "password": PASSWORD})
    maya = bearer(signup(client, "Maya Patel", MAYA))
    token = invite(client, gym, olga, kind="CLIENT", email=MAYA, practice_lead_email=ADA, reason="coordinates Maya")["token"]
    accept(client, token, maya)
    maya_id = client.get("/me", headers=maya).json()["client"]["id"]
    team = f"/clients/{maya_id}/care-team"
    body = {"provider_email": TOM, "discipline": "TRAINER", "org_id": gym["id"], "reason": "gym trainer"}
    assert client.post(f"{team}/members", json=body, headers=ada).status_code == 201

    signup_provider(client, "Pia Physio", PIA, "PHYSIO")
    return {"gym": gym["id"], "team": team}


def send(client: TestClient, by: str, to: str = MAYA, discipline: str = "PHYSIO") -> object:
    body = {"client_email": to, "discipline": discipline, "reason": "shoulder rehab"}
    return client.post("/care-invitations", json=body, headers=login(client, by))


def take(client: TestClient, token: str, by: str) -> object:
    return client.post("/care-invitations/accept", json={"token": token}, headers=login(client, by))


def members(client: TestClient, world: dict, viewer: str) -> list[dict]:
    response = client.get(world["team"], headers=login(client, viewer))
    assert response.status_code == 200, response.text
    return response.json()["members"]


def test_maya_has_a_gym_trainer_and_an_independent_physio(client, world):
    sent = send(client, PIA)
    assert sent.status_code == 201, sent.text
    joined = take(client, sent.json()["token"], MAYA)
    assert joined.status_code == 200, joined.text
    assert (joined.json()["org_context_id"], joined.json()["engagement"]) == (None, "ACTIVE")

    assert sorted((m["discipline"], m["org_context_id"]) for m in members(client, world, MAYA)) == sorted(
        [("TRAINER", world["gym"]), ("PHYSIO", None)]
    )
    assert [m["discipline"] for m in members(client, world, ADA)] == ["TRAINER"]  # the gym's slice only
    assert len(members(client, world, PIA)) == 2  # a member sees the whole team


def test_pia_runs_her_own_membership_and_maya_can_end_it(client, clock: FixedClock, world):
    pia = take(client, send(client, PIA).json()["token"], MAYA).json()
    clock.advance(DAY)
    step_back = {"engagement": "CONSULTING", "reason": "rehab finished"}
    consulting = client.post(f"{world['team']}/members/{pia['id']}/engagement", json=step_back, headers=login(client, PIA))
    assert consulting.status_code == 200, consulting.text

    clock.advance(DAY)
    end = f"{world['team']}/members/{consulting.json()['id']}/end"
    assert client.post(end, json={"reason": "r"}, headers=login(client, ADA)).status_code == 403  # not the gym's
    assert client.post(end, json={"reason": "Maya is done with physio"}, headers=login(client, MAYA)).status_code == 204


def test_only_the_invited_client_can_accept(client, world):
    token = send(client, PIA).json()["token"]
    signup(client, "Eve Elsewhere", "eve@example.com")
    assert take(client, token, "eve@example.com").status_code == 403


def test_it_works_once_and_expires_after_a_week(client, clock: FixedClock, world):
    token = send(client, PIA).json()["token"]
    assert take(client, token, MAYA).status_code == 200
    assert take(client, token, MAYA).status_code == 410

    late = send(client, PIA, to="sam@example.com").json()["token"]
    signup(client, "Sam", "sam@example.com")
    clock.advance(7 * DAY)
    assert take(client, late, "sam@example.com").status_code == 410


def test_only_providers_invite_in_disciplines_they_hold(client, world):
    assert send(client, MAYA, to="someone@example.com").status_code == 403  # Maya is not a provider
    assert send(client, PIA, discipline="PHYSICIAN").status_code == 422


def test_the_invitee_must_be_a_client(client, world):
    signup_provider(client, "Mia Massage", "mia@example.com", "MASSAGE")
    token = send(client, PIA, to="mia@example.com").json()["token"]
    assert take(client, token, "mia@example.com").status_code == 422


def test_a_physio_who_is_also_a_client_cannot_join_her_own_team(client, world):
    sam = bearer(signup(client, "Sam Cover", "sam@example.com"))  # a client
    client.post("/providers", json={"qualifications": ["PHYSIO"]}, headers=sam)  # and a physio
    token = send(client, "sam@example.com", to="sam@example.com").json()["token"]
    response = take(client, token, "sam@example.com")
    assert response.status_code == 422
    assert "own care team" in response.json()["detail"]


def test_unknown_token_and_no_sign_in(client, world):
    assert take(client, "not-a-real-token", MAYA).status_code == 404
    assert client.post("/care-invitations/accept", json={"token": "x"}).status_code == 401
