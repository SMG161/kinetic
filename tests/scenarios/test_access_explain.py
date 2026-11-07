"""/access/explain end to end: the policy answers with facts from care_team and directory,
wired in main.py. Maya's team is saved through the repository, since the care team
endpoints arrive in the next step."""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from kinetic import db
from kinetic.care_team.domain.facts import ClientFacts, Discipline, ProviderFacts
from kinetic.care_team.domain.model import CareTeam, Engagement
from kinetic.care_team.infrastructure.repositories import SqlCareTeamRepository
from kinetic.shared_kernel import ClientId, OrganizationId, PersonId, ProviderId
from tests.scenarios.conftest import T0
from tests.scenarios.helpers import PASSWORD, accept, bearer, invite, signup


def me(client: TestClient, headers: dict) -> dict:
    return client.get("/me", headers=headers).json()


@pytest.fixture
def gym(client: TestClient) -> dict:
    """IronWorks: Olga owns it, Ada is admin and Maya's practice lead, Tom trains there."""
    olga = bearer(signup(client, "Olga Owner", "olga@ironworks.example"))
    org = client.post("/orgs", json={"name": "IronWorks Gym"}, headers=olga).json()

    ada = bearer(signup(client, "Ada Admin", "ada@ironworks.example"))
    accept(client, invite(client, org, olga, kind="STAFF", email="ada@ironworks.example", role="ADMIN")["token"], ada)

    token = invite(client, org, olga, kind="PRACTITIONER", email="tom@ironworks.example", disciplines=["TRAINER"])["token"]
    tom = bearer(client.post("/invitations/accept", json={"token": token, "full_name": "Tom", "password": PASSWORD}).json()["tokens"])

    maya = bearer(signup(client, "Maya Patel", "maya@example.com"))
    token = invite(
        client, org, olga, kind="CLIENT", email="maya@example.com",
        practice_lead_email="ada@ironworks.example", reason="Ada coordinates Maya",
    )["token"]
    accept(client, token, maya)
    return {"org": org, "olga": olga, "ada": ada, "tom": tom, "maya": maya}


@pytest.fixture
def team(client: TestClient, gym: dict) -> CareTeam:
    """Maya's team: Tom as her trainer, in the gym's context."""
    tom_me, maya_me, ada_me = me(client, gym["tom"]), me(client, gym["maya"]), me(client, gym["ada"])
    gym_id = OrganizationId(UUID(gym["org"]["id"]))
    tom = ProviderFacts(
        ProviderId(UUID(tom_me["provider"]["id"])), PersonId(UUID(tom_me["id"])),
        frozenset({Discipline.TRAINER}), {gym_id: frozenset({Discipline.TRAINER})},
    )
    maya = ClientFacts(ClientId(UUID(maya_me["client"]["id"])), PersonId(UUID(maya_me["id"])), frozenset({gym_id}))
    team = CareTeam.for_client(maya)
    team.add_member(PersonId(UUID(ada_me["id"])), tom, maya, Discipline.TRAINER, gym_id, Engagement.ACTIVE, "trainer", T0)
    with db.get_session_factory().begin() as session:
        SqlCareTeamRepository(session).add(team)
    return team


def explain(client: TestClient, headers: dict, **params) -> dict:
    response = client.get("/access/explain", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_client_sees_her_whole_team(client, gym, team):
    answer = explain(client, gym["maya"], action="VIEW_TEAM", client_id=team.client_id)
    assert answer == {"allowed": True, "reason": "allowed: the client sees their whole team", "scope": None}


def test_the_practice_lead_sees_only_her_orgs_slice(client, gym, team):
    answer = explain(client, gym["ada"], action="VIEW_TEAM", client_id=team.client_id)
    assert answer["allowed"] and answer["scope"] == [gym["org"]["id"]]


def test_the_practice_lead_may_add_gym_members_but_not_solo_ones(client, gym, team):
    assert explain(client, gym["ada"], action="ADD_MEMBER", client_id=team.client_id, org_id=gym["org"]["id"])["allowed"]
    solo = explain(client, gym["ada"], action="ADD_MEMBER", client_id=team.client_id)
    assert solo == {"allowed": False, "reason": "denied: solo providers join by care invitation", "scope": None}


def test_the_trainer_sees_the_training_plan_but_not_the_medical_history(client, gym, team):
    plan = explain(client, gym["tom"], action="VIEW_RECORD", client_id=team.client_id, category="TRAINING_PLAN")
    history = explain(client, gym["tom"], action="VIEW_RECORD", client_id=team.client_id, category="MEDICAL_HISTORY")
    assert plan["reason"] == "allowed: member (ACTIVE TRAINER)"
    assert history == {"allowed": False, "reason": "denied: TRAINER cannot see MEDICAL_HISTORY", "scope": None}


def test_the_owner_is_not_on_the_team_and_gets_nothing(client, gym, team):
    """Olga owns the gym, but owning an org grants nothing on a client's team."""
    answer = explain(client, gym["olga"], action="VIEW_TEAM", client_id=team.client_id)
    assert answer["allowed"] is False


def test_a_client_with_no_team_yet_still_gets_an_answer(client, gym):
    maya_client_id = me(client, gym["maya"])["client"]["id"]
    assert explain(client, gym["maya"], action="VIEW_TEAM", client_id=maya_client_id)["allowed"]
    assert explain(client, gym["ada"], action="ADD_MEMBER", client_id=maya_client_id, org_id=gym["org"]["id"])["allowed"]


def test_an_unknown_client(client, gym):
    answer = explain(client, gym["maya"], action="VIEW_TEAM", client_id=uuid4())
    assert answer["reason"] == "denied: no such client"


def test_explain_needs_sign_in(client, gym, team):
    assert client.get("/access/explain", params={"action": "VIEW_TEAM", "client_id": str(team.client_id)}).status_code == 401
