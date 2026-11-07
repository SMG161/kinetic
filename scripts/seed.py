"""Seed the dev database with synthetic demo data, through the real HTTP API.

Every step is an ordinary API call made in-process (FastAPI's TestClient), so the
seed obeys exactly the same rules as any user and proves each endpoint works.
It also writes demo/seed.json (git-ignored) so the demo page can offer one-click
sign-in, ids and pending invitation tokens.

    uv run python scripts/seed.py           # refuses if the database has data
    uv run python scripts/seed.py --reset   # empties every context first

All people are synthetic. Every account uses DEMO_PASSWORD; it exists only for
local development.
"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from kinetic.db import get_engine
from kinetic.main import create_app

DEMO_PASSWORD = "kinetic-demo-2026"
SEED_FILE = Path(__file__).parents[1] / "demo" / "seed.json"
SCHEMAS = ["identity", "directory", "care_team", "records"]

accounts: list[dict] = []


def call(api: TestClient, method: str, path: str, expect: int, headers: dict | None = None, **body) -> dict:
    response = api.request(method, path, json=body or None, headers=headers)
    if response.status_code != expect:
        sys.exit(f"{method} {path} returned {response.status_code}, expected {expect}: {response.text}")
    return response.json() if response.content else {}


def bearer(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def signup(api: TestClient, name: str, email: str, summary: str, qualifications: tuple[str, ...] = ()) -> dict:
    """Self-signup: a client, or a provider (and not a client) when qualifications are given."""
    tokens = call(api, "POST", "/auth/signup", 201, full_name=name, email=email, password=DEMO_PASSWORD,
                  qualifications=list(qualifications))
    accounts.append({"name": name, "email": email, "summary": summary})
    return bearer(tokens)


def accept_as_new(api: TestClient, token: str, name: str, email: str, summary: str) -> dict:
    accepted = call(api, "POST", "/invitations/accept", 200, token=token, full_name=name, password=DEMO_PASSWORD)
    accounts.append({"name": name, "email": email, "summary": summary})
    return bearer(accepted["tokens"])


def invite(api: TestClient, org_id: str, headers: dict, **body) -> str:
    return call(api, "POST", f"/orgs/{org_id}/invitations", 201, headers=headers, **body)["token"]


def care_invite(api: TestClient, provider: dict, client_email: str, discipline: str, reason: str) -> str:
    body = {"client_email": client_email, "discipline": discipline, "reason": reason}
    return call(api, "POST", "/care-invitations", 201, headers=provider, **body)["token"]


def name_everyone(api: TestClient) -> dict[str, str]:
    """Person and provider ids to names, so the demo page can show people instead of UUIDs."""
    names = {}
    for account in accounts:
        tokens = call(api, "POST", "/auth/login", 200, email=account["email"], password=DEMO_PASSWORD)
        me = call(api, "GET", "/me", 200, headers=bearer(tokens))
        names[me["id"]] = account["name"]
        if me["provider"]:
            names[me["provider"]["id"]] = account["name"]
    return names


def database_has_data() -> bool:
    with get_engine().connect() as conn:
        return bool(conn.scalar(text("SELECT EXISTS (SELECT 1 FROM identity.person)")))


def empty_database() -> None:
    with get_engine().begin() as conn:
        tables = conn.scalars(
            text("SELECT format('%I.%I', schemaname, tablename) FROM pg_tables WHERE schemaname = ANY(:s)"),
            {"s": SCHEMAS},
        ).all()
        conn.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))


def seed(api: TestClient) -> dict:
    # Self-signup as clients.
    maya = signup(api, "Maya Patel", "maya@example.com", "Client. Served by IronWorks Gym and City Sports Clinic")
    olga = signup(api, "Olga Owner", "olga@ironworks.example", "Owner of IronWorks Gym")
    pia = signup(api, "Pia Physio", "pia@example.com", "Solo physio on Maya's team; also a client; has two pending invitations")
    call(api, "POST", "/providers", 201, headers=pia, qualifications=["PHYSIO"])

    # Self-signup as providers: not clients.
    chen = signup(api, "Dr Chen Wu", "chen@citysports.example", "Physician who founded City Sports Clinic and treats there",
                  ("PHYSICIAN",))
    sam = signup(api, "Sam Cover", "sam@example.com", "Solo physio covering Pia for two weeks", ("PHYSIO",))
    mia = signup(api, "Mia Massage", "mia@example.com", "Solo massage therapist on Maya's team", ("MASSAGE",))

    # Two organizations. The clinic owner also practises there: he invites himself and accepts.
    gym = call(api, "POST", "/orgs", 201, headers=olga, name="IronWorks Gym")["id"]
    clinic = call(api, "POST", "/orgs", 201, headers=chen, name="City Sports Clinic")["id"]
    token = invite(api, clinic, chen, kind="PRACTITIONER", email="chen@citysports.example", disciplines=["PHYSICIAN"])
    call(api, "POST", "/invitations/accept", 200, headers=chen, token=token)

    # Staff and a practitioner join IronWorks through invitations, as new people.
    token = invite(api, gym, olga, kind="STAFF", email="ada@ironworks.example", role="ADMIN")
    ada = accept_as_new(api, token, "Ada Admin", "ada@ironworks.example", "Admin at IronWorks Gym; Maya's current practice lead there")
    token = invite(api, gym, ada, kind="STAFF", email="dee@ironworks.example", role="FRONT_DESK")
    accept_as_new(api, token, "Dee Desk", "dee@ironworks.example", "Front desk at IronWorks Gym; Maya's first practice lead")
    token = invite(api, gym, olga, kind="PRACTITIONER", email="tom@ironworks.example", disciplines=["TRAINER"])
    tom = accept_as_new(api, token, "Tom Trainer", "tom@ironworks.example", "Maya's trainer at IronWorks Gym (invited, so not a client)")

    # IronWorks invites Maya as a client; she accepts signed in, which is her consent.
    token = invite(api, gym, olga, kind="CLIENT", email="maya@example.com",
                   practice_lead_email="dee@ironworks.example", reason="Dee coordinates new members")
    call(api, "POST", "/invitations/accept", 200, headers=maya, token=token)
    maya_client_id = call(api, "GET", "/me", 200, headers=maya)["client"]["id"]

    # The practice lead changes; the history keeps both periods and both reasons.
    call(api, "POST", f"/orgs/{gym}/clients/{maya_client_id}/practice-lead", 200, headers=ada,
         practice_lead_email="ada@ironworks.example", reason="Dee is on leave for two weeks")

    # The clinic also serves Maya, again through an invitation she accepts.
    token = invite(api, clinic, chen, kind="CLIENT", email="maya@example.com",
                   practice_lead_email="chen@citysports.example", reason="Sports physician for Maya's shoulder")
    call(api, "POST", "/invitations/accept", 200, headers=maya, token=token)

    # Maya's care team. Each org adds its own people; solo providers join by care invitation.
    team = f"/clients/{maya_client_id}/care-team"
    call(api, "POST", f"{team}/members", 201, headers=ada, provider_email="tom@ironworks.example",
         discipline="TRAINER", org_id=gym, reason="Strength training at the gym")
    call(api, "POST", f"{team}/members", 201, headers=chen, provider_email="chen@citysports.example",
         discipline="PHYSICIAN", org_id=clinic, reason="Sports physician for the underlying issue")
    token = care_invite(api, pia, "maya@example.com", "PHYSIO", "Rehab for Maya's shoulder")
    pia_membership = call(api, "POST", "/care-invitations/accept", 200, headers=maya, token=token)["id"]
    token = care_invite(api, mia, "maya@example.com", "MASSAGE", "Monthly massage")
    call(api, "POST", "/care-invitations/accept", 200, headers=maya, token=token)

    # Sam covers Pia for two weeks. A window cannot start in the past, so it starts in a minute.
    starts = datetime.now(UTC) + timedelta(minutes=1)
    call(api, "POST", f"{team}/members/{pia_membership}/coverages", 201, headers=pia,
         covering_provider_email="sam@example.com", reason="Pia is on leave",
         starts_at=starts.isoformat(), ends_at=(starts + timedelta(days=14)).isoformat())

    # Records in different categories, so each person sees a different slice.
    records = f"/clients/{maya_client_id}/records"
    for author, category, body in [
        (chen, "MEDICAL_HISTORY", "Synthetic: previous left shoulder dislocation."),
        (pia, "ASSESSMENT", "Synthetic: reduced external rotation, right shoulder."),
        (pia, "ASSESSMENT_SUMMARY", "Synthetic: no overhead pressing for six weeks."),
        (tom, "TRAINING_PLAN", "Synthetic: lower body focus, three sessions a week."),
        (tom, "SESSION_NOTE", "Synthetic: good session, no shoulder pain reported."),
        (mia, "MASSAGE_PLAN", "Synthetic: monthly, avoid the right shoulder."),
    ]:
        call(api, "POST", records, 201, headers=author, category=category, body=body)

    # Left pending so they can be accepted from the demo page.
    pending = [
        {"description": "Nina joins IronWorks as front desk (accept as a new person)", "email": "nina@ironworks.example",
         "token": invite(api, gym, olga, kind="STAFF", email="nina@ironworks.example", role="FRONT_DESK")},
        {"description": "City Sports Clinic invites Pia as a physio (sign in as Pia, then accept)", "email": "pia@example.com",
         "token": invite(api, clinic, chen, kind="PRACTITIONER", email="pia@example.com", disciplines=["PHYSIO"])},
    ]
    pending_care = [
        {"description": "Sam invites Pia as his client (sign in as Pia, then accept)", "email": "pia@example.com",
         "token": care_invite(api, sam, "pia@example.com", "PHYSIO", "Pia's own back pain")},
    ]
    return {
        "password": DEMO_PASSWORD,
        "accounts": accounts,
        "organizations": {"IronWorks Gym": gym, "City Sports Clinic": clinic},
        "clients": {"Maya Patel": maya_client_id},
        "pending_invitations": pending,
        "pending_care_invitations": pending_care,
        "names": name_everyone(api),
    }


def main() -> None:
    if database_has_data():
        if "--reset" not in sys.argv:
            sys.exit("The dev database already has data. Run with --reset to empty every context first.")
        empty_database()
    with TestClient(create_app()) as api:
        data = seed(api)
    SEED_FILE.write_text(json.dumps(data, indent=2))
    print(f"Seeded {len(data['accounts'])} accounts and 2 organizations. Wrote {SEED_FILE}.")
    for account in data["accounts"]:
        print(f"  {account['email']:<28} {account['summary']}")


if __name__ == "__main__":
    main()
