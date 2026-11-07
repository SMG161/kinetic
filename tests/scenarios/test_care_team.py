"""Brief, build target 2: the care team through the HTTP API, every command behind access.

Maya trains at IronWorks Gym (Ada is her practice lead there; Tom and Tess are trainers)
and is treated at City Sports Clinic (Dr Chen leads her there and treats; Pia is a
clinic physio). Mia is a solo massage therapist who is not on Maya's team.
Solo providers joining by invitation arrive with care invitations.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from kinetic.shared_kernel import FixedClock
from tests.scenarios.conftest import T0
from tests.scenarios.helpers import PASSWORD, accept, bearer, invite, login, signup

DAY = timedelta(days=1)


def signup_provider(client: TestClient, name: str, email: str, discipline: str) -> dict:
    body = {"full_name": name, "email": email, "password": PASSWORD, "qualifications": [discipline]}
    return bearer(client.post("/auth/signup", json=body).json())


def join_as_new(client: TestClient, token: str, name: str) -> dict:
    return bearer(client.post("/invitations/accept", json={"token": token, "full_name": name, "password": PASSWORD}).json()["tokens"])


@pytest.fixture
def world(client: TestClient) -> dict:
    olga = bearer(signup(client, "Olga Owner", "olga@ironworks.example"))
    gym = client.post("/orgs", json={"name": "IronWorks Gym"}, headers=olga).json()
    ada = bearer(signup(client, "Ada Admin", "ada@ironworks.example"))
    accept(client, invite(client, gym, olga, kind="STAFF", email="ada@ironworks.example", role="ADMIN")["token"], ada)
    trainer = {"kind": "PRACTITIONER", "disciplines": ["TRAINER"]}
    join_as_new(client, invite(client, gym, olga, email="tom@ironworks.example", **trainer)["token"], "Tom")
    join_as_new(client, invite(client, gym, olga, email="tess@ironworks.example", **trainer)["token"], "Tess")

    chen = signup_provider(client, "Dr Chen", "chen@citysports.example", "PHYSICIAN")
    clinic = client.post("/orgs", json={"name": "City Sports Clinic"}, headers=chen).json()
    token = invite(client, clinic, chen, kind="PRACTITIONER", email="chen@citysports.example", disciplines=["PHYSICIAN"])["token"]
    accept(client, token, chen)
    pia = signup_provider(client, "Pia Physio", "pia@example.com", "PHYSIO")
    accept(client, invite(client, clinic, chen, kind="PRACTITIONER", email="pia@example.com", disciplines=["PHYSIO"])["token"], pia)

    maya = bearer(signup(client, "Maya Patel", "maya@example.com"))
    for org, lead in [(gym, "ada@ironworks.example"), (clinic, "chen@citysports.example")]:
        token = invite(client, org, olga if org is gym else chen, kind="CLIENT", email="maya@example.com",
                       practice_lead_email=lead, reason="coordinates Maya")["token"]
        accept(client, token, maya)

    signup_provider(client, "Mia Massage", "mia@example.com", "MASSAGE")
    maya_id = client.get("/me", headers=maya).json()["client"]["id"]
    return {"gym": gym["id"], "clinic": clinic["id"], "maya_id": maya_id, "team": f"/clients/{maya_id}/care-team"}


def as_(client: TestClient, email: str) -> dict:
    """Sign in (again): tests move the clock past the 15-minute access token."""
    return login(client, email)


def add(client: TestClient, world: dict, by: str, provider: str, discipline: str, org: str | None) -> object:
    body = {"provider_email": provider, "discipline": discipline, "org_id": world[org] if org else None, "reason": f"{discipline} for Maya"}
    return client.post(f"{world['team']}/members", json=body, headers=as_(client, by))


def team(client: TestClient, world: dict, viewer: str, **params) -> dict:
    response = client.get(world["team"], params=params, headers=as_(client, viewer))
    assert response.status_code == 200, response.text
    return response.json()


def explain(client: TestClient, world: dict, who: str, **params) -> dict:
    return client.get("/access/explain", params={"client_id": world["maya_id"], **params}, headers=as_(client, who)).json()


ADA, CHEN, MAYA = "ada@ironworks.example", "chen@citysports.example", "maya@example.com"
TOM, TESS, PIA, MIA = "tom@ironworks.example", "tess@ironworks.example", "pia@example.com", "mia@example.com"


def test_trainer_physio_and_physician_at_once_across_orgs(client, world):
    assert add(client, world, ADA, TOM, "TRAINER", "gym").status_code == 201
    assert add(client, world, CHEN, PIA, "PHYSIO", "clinic").status_code == 201
    assert add(client, world, CHEN, CHEN, "PHYSICIAN", "clinic").status_code == 201

    members = team(client, world, MAYA)["members"]
    assert sorted((m["discipline"], m["org_context_id"], m["engagement"]) for m in members) == sorted([
        ("TRAINER", world["gym"], "ACTIVE"),
        ("PHYSIO", world["clinic"], "ACTIVE"),
        ("PHYSICIAN", world["clinic"], "ACTIVE"),
    ])


def test_each_org_runs_only_its_own_side(client, world):
    to_clinic = add(client, world, ADA, PIA, "PHYSIO", "clinic")
    assert to_clinic.status_code == 403
    assert to_clinic.json()["detail"] == "denied: only that org's practice lead adds its members"
    assert add(client, world, MIA, MIA, "MASSAGE", None).status_code == 403  # an outsider adding herself
    assert add(client, world, MAYA, TOM, "TRAINER", "gym").status_code == 403  # the client does not staff the gym


def test_a_practice_lead_sees_only_their_orgs_slice(client, world):
    add(client, world, ADA, TOM, "TRAINER", "gym")
    add(client, world, CHEN, PIA, "PHYSIO", "clinic")

    ada_view = team(client, world, ADA)
    assert [m["org_context_id"] for m in ada_view["members"]] == [world["gym"]]
    assert [lead["organization_id"] for lead in ada_view["practice_leads"]] == [world["gym"]]
    assert len(team(client, world, MAYA)["members"]) == 2


def test_domain_rules_come_back_as_clear_errors(client, world):
    add(client, world, ADA, TOM, "TRAINER", "gym")
    assert add(client, world, ADA, TOM, "TRAINER", "gym").status_code == 409  # already on the team
    assert add(client, world, ADA, TESS, "PHYSIO", "gym").status_code == 422  # not a physio at the gym
    assert add(client, world, ADA, "nobody@example.com", "TRAINER", "gym").status_code == 404


def test_two_week_coverage_then_handback(client, clock: FixedClock, world):
    tom = add(client, world, ADA, TOM, "TRAINER", "gym").json()
    cover = {"covering_provider_email": TESS, "reason": "Tom on leave",
             "starts_at": (T0 + DAY).isoformat(), "ends_at": (T0 + 15 * DAY).isoformat()}
    response = client.post(f"{world['team']}/members/{tom['id']}/coverages", json=cover, headers=as_(client, ADA))
    assert response.status_code == 201, response.text
    coverage_id = response.json()["id"]

    clock.advance(2 * DAY)  # Tess is covering
    covering = explain(client, world, TESS, action="VIEW_RECORD", category="TRAINING_PLAN")
    assert covering["allowed"] and "covering" in covering["reason"]
    end = client.post(f"{world['team']}/members/{tom['id']}/end", json={"reason": "r"}, headers=as_(client, TESS))
    assert end.status_code == 403  # a cover cannot manage the team

    clock.advance(3 * DAY)  # day 5: Tom is back early and Ada hands back
    handback = f"{world['team']}/members/{tom['id']}/coverages/{coverage_id}/end"
    assert client.post(handback, json={"reason": "Tom is back"}, headers=as_(client, ADA)).status_code == 204
    after = explain(client, world, TESS, action="VIEW_RECORD", category="TRAINING_PLAN")
    assert after == {"allowed": False, "reason": f"denied: coverage ended at {(T0 + 5 * DAY).isoformat()}", "scope": None}


def test_the_physio_steps_back_and_history_keeps_both_periods(client, clock: FixedClock, world):
    pia = add(client, world, CHEN, PIA, "PHYSIO", "clinic").json()
    clock.advance(30 * DAY)
    response = client.post(
        f"{world['team']}/members/{pia['id']}/engagement",
        json={"engagement": "CONSULTING", "reason": "rehab finished"},
        headers=as_(client, CHEN),
    )
    assert response.status_code == 200, response.text

    before = team(client, world, MAYA, as_of=(T0 + 29 * DAY).isoformat())["members"]
    now = team(client, world, MAYA)["members"]
    assert [m["engagement"] for m in before] == ["ACTIVE"]
    assert [m["engagement"] for m in now] == ["CONSULTING"]

    history = client.get(f"{world['team']}/history", headers=as_(client, MAYA)).json()
    assert len(history["memberships"]) == 2  # closed, not overwritten
    assert [(e["type"], e["reason"]) for e in history["events"]] == [
        ("MEMBER_ADDED", "PHYSIO for Maya"),
        ("ENGAGEMENT_CHANGED", "rehab finished"),
    ]


def test_maya_discharges_the_gym(client, clock: FixedClock, world):
    add(client, world, ADA, TOM, "TRAINER", "gym")
    add(client, world, CHEN, PIA, "PHYSIO", "clinic")
    clock.advance(3 * DAY)
    discharge = f"{world['team']}/orgs/{world['gym']}/discharge"
    assert client.post(discharge, json={"reason": "Maya left the gym"}, headers=as_(client, MAYA)).status_code == 204

    assert [m["org_context_id"] for m in team(client, world, MAYA)["members"]] == [world["clinic"]]
    ada = as_(client, ADA)
    assert client.get(world["team"], headers=ada).status_code == 403  # no longer her practice lead
    assert client.get(f"/orgs/{world['gym']}/clients/{world['maya_id']}", headers=ada).status_code == 404
    events = client.get(f"{world['team']}/history", headers=as_(client, MAYA)).json()["events"]
    assert events[-1]["type"] == "ORGANIZATION_DISCHARGED"


def test_viewing_needs_a_relationship_to_the_team(client, world):
    add(client, world, ADA, TOM, "TRAINER", "gym")
    assert client.get(world["team"], headers=as_(client, MIA)).status_code == 403
    assert client.get(world["team"]).status_code == 401
