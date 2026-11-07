"""Brief: access is not all-or-nothing. The physician sees medical history and the rehab
assessment; the massage therapist does not. Seeing a record and acting on it (writing
notes) are separate questions. Every read and write goes through access.

Maya's team: Tom (IronWorks trainer), Pia (clinic physio), Dr Chen (clinic physician,
also her practice lead there) and Mia (a solo massage therapist, by care invitation).
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from kinetic.shared_kernel import FixedClock
from tests.scenarios.conftest import T0
from tests.scenarios.helpers import PASSWORD, accept, bearer, invite, login, signup

DAY = timedelta(days=1)
ADA, CHEN, MAYA = "ada@ironworks.example", "chen@citysports.example", "maya@example.com"
TOM, PIA, MIA, SAM = "tom@ironworks.example", "pia@example.com", "mia@example.com", "sam@example.com"


def signup_provider(client: TestClient, name: str, email: str, discipline: str) -> dict:
    body = {"full_name": name, "email": email, "password": PASSWORD, "qualifications": [discipline]}
    return bearer(client.post("/auth/signup", json=body).json())


@pytest.fixture
def world(client: TestClient) -> dict:
    olga = bearer(signup(client, "Olga Owner", "olga@ironworks.example"))
    gym = client.post("/orgs", json={"name": "IronWorks Gym"}, headers=olga).json()
    ada = bearer(signup(client, "Ada Admin", ADA))
    accept(client, invite(client, gym, olga, kind="STAFF", email=ADA, role="ADMIN")["token"], ada)
    token = invite(client, gym, olga, kind="PRACTITIONER", email=TOM, disciplines=["TRAINER"])["token"]
    client.post("/invitations/accept", json={"token": token, "full_name": "Tom", "password": PASSWORD})

    chen = signup_provider(client, "Dr Chen", CHEN, "PHYSICIAN")
    clinic = client.post("/orgs", json={"name": "City Sports Clinic"}, headers=chen).json()
    accept(client, invite(client, clinic, chen, kind="PRACTITIONER", email=CHEN, disciplines=["PHYSICIAN"])["token"], chen)
    pia = signup_provider(client, "Pia Physio", PIA, "PHYSIO")
    accept(client, invite(client, clinic, chen, kind="PRACTITIONER", email=PIA, disciplines=["PHYSIO"])["token"], pia)

    maya = bearer(signup(client, "Maya Patel", MAYA))
    for org, by, lead in [(gym, olga, ADA), (clinic, chen, CHEN)]:
        accept(client, invite(client, org, by, kind="CLIENT", email=MAYA, practice_lead_email=lead, reason="r")["token"], maya)
    maya_id = client.get("/me", headers=maya).json()["client"]["id"]
    team = f"/clients/{maya_id}/care-team"

    members = {}
    for by, who, discipline, org in [(ADA, TOM, "TRAINER", gym), (CHEN, PIA, "PHYSIO", clinic), (CHEN, CHEN, "PHYSICIAN", clinic)]:
        body = {"provider_email": who, "discipline": discipline, "org_id": org["id"], "reason": "r"}
        response = client.post(f"{team}/members", json=body, headers=login(client, by))
        assert response.status_code == 201, response.text
        members[who] = response.json()["id"]

    signup_provider(client, "Mia Massage", MIA, "MASSAGE")
    sent = client.post("/care-invitations", json={"client_email": MAYA, "discipline": "MASSAGE", "reason": "r"}, headers=login(client, MIA))
    assert client.post("/care-invitations/accept", json={"token": sent.json()["token"]}, headers=maya).status_code == 200

    signup_provider(client, "Sam Cover", SAM, "PHYSIO")
    return {"records": f"/clients/{maya_id}/records", "team": team, "members": members}


def write(client: TestClient, world: dict, by: str, category: str, body: str = "a note") -> object:
    return client.post(world["records"], json={"category": category, "body": body}, headers=login(client, by))


def visible(client: TestClient, world: dict, viewer: str) -> list[str]:
    response = client.get(world["records"], headers=login(client, viewer))
    assert response.status_code == 200, response.text
    return [r["category"] for r in response.json()]


@pytest.fixture
def notes(client: TestClient, world: dict) -> None:
    for by, category in [(CHEN, "MEDICAL_HISTORY"), (PIA, "ASSESSMENT"), (TOM, "TRAINING_PLAN"), (TOM, "SESSION_NOTE")]:
        assert write(client, world, by, category).status_code == 201


def test_the_physician_sees_medical_history_and_the_assessment(client, world, notes):
    assert visible(client, world, CHEN) == ["MEDICAL_HISTORY", "ASSESSMENT", "TRAINING_PLAN", "SESSION_NOTE"]


def test_the_massage_therapist_does_not(client, world, notes):
    assert visible(client, world, MIA) == ["SESSION_NOTE"]
    assert visible(client, world, TOM) == ["TRAINING_PLAN", "SESSION_NOTE"]


def test_writing_needs_the_category_too(client, world):
    response = write(client, world, TOM, "MEDICAL_HISTORY")
    assert response.status_code == 403
    assert response.json()["detail"] == "denied: TRAINER cannot see MEDICAL_HISTORY"


def test_a_physio_who_steps_back_still_reads_but_no_longer_writes(client, clock: FixedClock, world, notes):
    clock.advance(DAY)
    step_back = {"engagement": "CONSULTING", "reason": "rehab finished"}
    pia = world["members"][PIA]
    assert client.post(f"{world['team']}/members/{pia}/engagement", json=step_back, headers=login(client, CHEN)).status_code == 200

    assert "ASSESSMENT" in visible(client, world, PIA)
    response = write(client, world, PIA, "ASSESSMENT")
    assert (response.status_code, response.json()["detail"]) == (403, "denied: CONSULTING members cannot WRITE_NOTE")


def test_a_cover_writes_during_the_window_and_sees_nothing_after(client, clock: FixedClock, world):
    cover = {"covering_provider_email": SAM, "reason": "Pia on leave",
             "starts_at": (T0 + DAY).isoformat(), "ends_at": (T0 + 15 * DAY).isoformat()}
    path = f"{world['team']}/members/{world['members'][PIA]}/coverages"
    assert client.post(path, json=cover, headers=login(client, CHEN)).status_code == 201

    clock.advance(2 * DAY)
    assert write(client, world, SAM, "CLINICAL_NOTE", "covering for Pia").status_code == 201

    clock.advance(14 * DAY)  # day 16
    response = client.get(world["records"], headers=login(client, SAM))
    assert response.status_code == 403
    assert response.json()["detail"] == f"denied: coverage ended at {(T0 + 15 * DAY).isoformat()}"


def test_an_alumni_trainer_sees_only_what_he_wrote(client, clock: FixedClock, world, notes):
    assert write(client, world, CHEN, "TRAINING_PLAN", "physician's plan").status_code == 201
    clock.advance(DAY)
    alumni = {"engagement": "ALUMNI", "reason": "Maya paused training"}
    tom = world["members"][TOM]
    assert client.post(f"{world['team']}/members/{tom}/engagement", json=alumni, headers=login(client, ADA)).status_code == 200

    records = client.get(world["records"], headers=login(client, TOM)).json()
    assert [r["category"] for r in records] == ["TRAINING_PLAN", "SESSION_NOTE"]  # his two, not Chen's plan
    assert write(client, world, TOM, "SESSION_NOTE").status_code == 403


def test_the_client_reads_everything_and_writes_nothing(client, world, notes):
    assert len(visible(client, world, MAYA)) == 4
    assert write(client, world, MAYA, "SESSION_NOTE").status_code == 403


def test_a_practice_lead_and_a_stranger_see_no_records(client, world, notes):
    assert client.get(world["records"], headers=login(client, ADA)).status_code == 403  # Ada leads, but does not treat
    signup(client, "Eve Elsewhere", "eve@example.com")
    assert client.get(world["records"], headers=login(client, "eve@example.com")).status_code == 403
    assert client.get(world["records"]).status_code == 401


def test_a_record_needs_text(client, world):
    assert write(client, world, PIA, "ASSESSMENT", "   ").status_code == 422
