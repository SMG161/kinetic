"""Cases the brief did not list but the model must express (docs/ARCHITECTURE.md, "Extra cases found").

The rest of that table is covered where it belongs: leads in test_client_relationships,
discharge in test_care_team, self-treatment in test_care_invitations.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from kinetic.shared_kernel import FixedClock
from tests.scenarios.conftest import T0
from tests.scenarios.helpers import PASSWORD, accept, bearer, invite, login, signup

DAY = timedelta(days=1)
ADA, MAYA, NINA = "ada@ironworks.example", "maya@example.com", "nina@example.com"
TOM, TESS, PIA, SAM = "tom@ironworks.example", "tess@ironworks.example", "pia@example.com", "sam@example.com"


def signup_provider(client: TestClient, name: str, email: str, discipline: str) -> dict:
    body = {"full_name": name, "email": email, "password": PASSWORD, "qualifications": [discipline]}
    return bearer(client.post("/auth/signup", json=body).json())


@pytest.fixture
def world(client: TestClient) -> dict:
    """IronWorks serves Maya, led by Ada. Tom, Tess and Pia work there; Sam is a solo physio."""
    olga = bearer(signup(client, "Olga Owner", "olga@ironworks.example"))
    gym = client.post("/orgs", json={"name": "IronWorks Gym"}, headers=olga).json()
    ada = bearer(signup(client, "Ada Admin", ADA))
    accept(client, invite(client, gym, olga, kind="STAFF", email=ADA, role="ADMIN")["token"], ada)
    for email, name, discipline in [(TOM, "Tom", "TRAINER"), (TESS, "Tess", "TRAINER"), (PIA, "Pia", "PHYSIO")]:
        token = invite(client, gym, olga, kind="PRACTITIONER", email=email, disciplines=[discipline])["token"]
        client.post("/invitations/accept", json={"token": token, "full_name": name, "password": PASSWORD})
    signup_provider(client, "Sam Cover", SAM, "PHYSIO")

    maya = bearer(signup(client, "Maya Patel", MAYA))
    token = invite(client, gym, olga, kind="CLIENT", email=MAYA, practice_lead_email=ADA, reason="r")["token"]
    accept(client, token, maya)
    return {"gym": gym, "olga": olga, "team": team_of(client, maya)}


def team_of(client: TestClient, headers: dict) -> str:
    return f"/clients/{client.get('/me', headers=headers).json()['client']['id']}/care-team"


def add(client: TestClient, team: str, world: dict, by: str, who: str, discipline: str) -> dict:
    body = {"provider_email": who, "discipline": discipline, "org_id": world["gym"]["id"], "reason": "gym member"}
    response = client.post(f"{team}/members", json=body, headers=login(client, by))
    assert response.status_code == 201, response.text
    return response.json()


def join_solo(client: TestClient, provider: str, client_email: str, discipline: str) -> dict:
    body = {"client_email": client_email, "discipline": discipline, "reason": "seeing them on my own"}
    sent = client.post("/care-invitations", json=body, headers=login(client, provider))
    assert sent.status_code == 201, sent.text
    joined = client.post("/care-invitations/accept", json={"token": sent.json()["token"]}, headers=login(client, client_email))
    assert joined.status_code == 200, joined.text
    return joined.json()


def explain(client: TestClient, who: str, team: str, **params) -> dict:
    client_id = team.split("/")[2]
    return client.get("/access/explain", params={"client_id": client_id, **params}, headers=login(client, who)).json()


def test_a_physio_leaves_the_gym_goes_independent_and_keeps_the_client(client, clock: FixedClock, world):
    team = world["team"]
    at_gym = add(client, team, world, ADA, PIA, "PHYSIO")
    clock.advance(30 * DAY)

    ended = client.post(f"{team}/members/{at_gym['id']}/end", json={"reason": "Pia left the gym"}, headers=login(client, ADA))
    assert ended.status_code == 204
    solo = join_solo(client, PIA, MAYA, "PHYSIO")

    history = client.get(f"{team}/history", headers=login(client, MAYA)).json()["memberships"]
    assert [m["org_context_id"] for m in history] == [world["gym"]["id"], None]
    assert history[0]["valid_to"] == history[1]["valid_from"] == solo["valid_from"]  # no gap, no overlap


def test_an_independent_physios_colleague_covers_with_no_shared_org(client, clock: FixedClock, world):
    team = world["team"]
    pia = join_solo(client, PIA, MAYA, "PHYSIO")  # Pia still works at the gym; this membership is solo
    cover = {"covering_provider_email": SAM, "reason": "Pia on leave",
             "starts_at": (T0 + DAY).isoformat(), "ends_at": (T0 + 15 * DAY).isoformat()}
    scheduled = client.post(f"{team}/members/{pia['id']}/coverages", json=cover, headers=login(client, PIA))
    assert scheduled.status_code == 201, scheduled.text

    clock.advance(2 * DAY)
    during = explain(client, SAM, team, action="VIEW_RECORD", category="ASSESSMENT")
    assert during["allowed"] and "covering" in during["reason"]
    clock.advance(14 * DAY)
    assert not explain(client, SAM, team, action="VIEW_RECORD", category="ASSESSMENT")["allowed"]


def test_a_provider_works_at_a_gym_and_also_sees_clients_on_their_own(client, clock: FixedClock, world):
    tom_at_gym = add(client, world["team"], world, ADA, TOM, "TRAINER")
    nina = bearer(signup(client, "Nina Solo", NINA))
    tom_solo = join_solo(client, TOM, NINA, "TRAINER")
    nina_team = team_of(client, nina)
    clock.advance(DAY)
    step_back = {"engagement": "CONSULTING", "reason": "lighter plan"}

    on_maya = client.post(f"{world['team']}/members/{tom_at_gym['id']}/engagement", json=step_back, headers=login(client, TOM))
    assert on_maya.status_code == 403  # on Maya's team the gym runs his membership
    on_nina = client.post(f"{nina_team}/members/{tom_solo['id']}/engagement", json=step_back, headers=login(client, TOM))
    assert on_nina.status_code == 200  # on Nina's team he is his own lead
    assert client.get(nina_team, headers=login(client, ADA)).status_code == 403  # the gym has no part in Nina's team


def test_a_gym_trainer_who_is_also_a_client_of_the_gym(client, world):
    token = invite(client, world["gym"], world["olga"], kind="CLIENT", email=TESS, practice_lead_email=ADA, reason="r")["token"]
    tess = login(client, TESS)
    assert accept(client, token, tess).status_code == 200
    own_team = team_of(client, tess)

    body = {"provider_email": TESS, "discipline": "TRAINER", "org_id": world["gym"]["id"], "reason": "r"}
    joining = client.post(f"{own_team}/members", json=body, headers=login(client, ADA))
    assert joining.status_code == 422  # never a member of her own team
    assert "own care team" in joining.json()["detail"]

    add(client, world["team"], world, ADA, TESS, "TRAINER")  # she does train Maya
    own = explain(client, TESS, own_team, action="VIEW_RECORD", category="MEDICAL_HISTORY")
    assert own["reason"] == "allowed: the client sees their own records"  # as the client, not as a trainer
    assert not explain(client, TESS, world["team"], action="VIEW_RECORD", category="MEDICAL_HISTORY")["allowed"]
    assert not explain(client, TESS, own_team, action="WRITE_NOTE", category="TRAINING_PLAN")["allowed"]
