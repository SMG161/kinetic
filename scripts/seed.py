"""Seed the dev database with synthetic demo data, through the real HTTP API.

Every step is an ordinary API call made in-process (FastAPI's TestClient), so the
seed obeys exactly the same rules as any user and proves each endpoint works.
It also writes demo/seed.json (git-ignored) so the demo page can offer one-click
sign-in, ids and pending invitation tokens.

    uv run python scripts/seed.py           # refuses if the database has data
    uv run python scripts/seed.py --reset   # empties identity and directory first

All people are synthetic. Every account uses DEMO_PASSWORD; it exists only for
local development.
"""

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from kinetic.db import get_engine
from kinetic.main import create_app

DEMO_PASSWORD = "kinetic-demo-2026"
SEED_FILE = Path(__file__).parents[1] / "demo" / "seed.json"
SCHEMAS = ["identity", "directory"]

accounts: list[dict] = []


def call(api: TestClient, method: str, path: str, expect: int, headers: dict | None = None, **body) -> dict:
    response = api.request(method, path, json=body or None, headers=headers)
    if response.status_code != expect:
        sys.exit(f"{method} {path} returned {response.status_code}, expected {expect}: {response.text}")
    return response.json() if response.content else {}


def bearer(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def signup(api: TestClient, name: str, email: str, summary: str) -> dict:
    tokens = call(api, "POST", "/auth/signup", 201, full_name=name, email=email, password=DEMO_PASSWORD)
    accounts.append({"name": name, "email": email, "summary": summary})
    return bearer(tokens)


def accept_as_new(api: TestClient, token: str, name: str, email: str, summary: str) -> dict:
    accepted = call(api, "POST", "/invitations/accept", 200, token=token, full_name=name, password=DEMO_PASSWORD)
    accounts.append({"name": name, "email": email, "summary": summary})
    return bearer(accepted["tokens"])


def invite(api: TestClient, org_id: str, headers: dict, **body) -> str:
    return call(api, "POST", f"/orgs/{org_id}/invitations", 201, headers=headers, **body)["token"]


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
    # Self-signup: each of these becomes a client, and some also register as providers.
    maya = signup(api, "Maya Patel", "maya@example.com", "Client. Served by IronWorks Gym and City Sports Clinic")
    olga = signup(api, "Olga Owner", "olga@ironworks.example", "Owner of IronWorks Gym")
    chen = signup(api, "Dr Chen Wu", "chen@citysports.example", "Owner of City Sports Clinic who also treats (physician)")
    pia = signup(api, "Pia Physio", "pia@example.com", "Independent physio, also a client; has a pending clinic invitation")
    sam = signup(api, "Sam Cover", "sam@example.com", "Independent physio (Pia's covering colleague later)")
    mia = signup(api, "Mia Massage", "mia@example.com", "Independent massage therapist")

    call(api, "POST", "/providers", 201, headers=chen, qualifications=["PHYSICIAN"])
    call(api, "POST", "/providers", 201, headers=pia, qualifications=["PHYSIO"])
    call(api, "POST", "/providers", 201, headers=sam, qualifications=["PHYSIO"])
    call(api, "POST", "/providers", 201, headers=mia, qualifications=["MASSAGE"])

    # Two organizations; the clinic owner also practises there.
    gym = call(api, "POST", "/orgs", 201, headers=olga, name="IronWorks Gym")["id"]
    clinic = call(api, "POST", "/orgs", 201, headers=chen, name="City Sports Clinic")["id"]
    call(api, "POST", f"/orgs/{clinic}/staff", 201, headers=chen,
         email="chen@citysports.example", role="PRACTITIONER", disciplines=["PHYSICIAN"])

    # Staff and a practitioner join IronWorks through invitations, as new people.
    token = invite(api, gym, olga, kind="STAFF", email="ada@ironworks.example", role="ADMIN")
    ada = accept_as_new(api, token, "Ada Admin", "ada@ironworks.example", "Admin at IronWorks Gym; Maya's current practice lead there")
    token = invite(api, gym, ada, kind="STAFF", email="dee@ironworks.example", role="FRONT_DESK")
    accept_as_new(api, token, "Dee Desk", "dee@ironworks.example", "Front desk at IronWorks Gym; Maya's first practice lead")
    token = invite(api, gym, olga, kind="PRACTITIONER", email="tom@ironworks.example", disciplines=["TRAINER"])
    accept_as_new(api, token, "Tom Trainer", "tom@ironworks.example", "Trainer at IronWorks Gym (invited, so not a client)")

    # IronWorks invites Maya as a client; she accepts signed in, which is her consent.
    token = invite(api, gym, olga, kind="CLIENT", email="maya@example.com",
                   practice_lead_email="dee@ironworks.example", reason="Dee coordinates new members")
    call(api, "POST", "/invitations/accept", 200, headers=maya, token=token)
    maya_client_id = call(api, "GET", "/me", 200, headers=maya)["client"]["id"]

    # The practice lead changes; the history keeps both periods and both reasons.
    call(api, "POST", f"/orgs/{gym}/clients/{maya_client_id}/practice-lead", 200, headers=ada,
         practice_lead_email="ada@ironworks.example", reason="Dee is on leave for two weeks")

    # The clinic also serves Maya, started directly (the walk-in path).
    call(api, "POST", f"/orgs/{clinic}/clients", 201, headers=chen, client_email="maya@example.com",
         practice_lead_email="chen@citysports.example", reason="Sports physician for Maya's shoulder")

    # Left pending so they can be accepted from the demo page.
    pending = [
        {"description": "Nina joins IronWorks as front desk (accept as a new person)", "email": "nina@ironworks.example",
         "token": invite(api, gym, olga, kind="STAFF", email="nina@ironworks.example", role="FRONT_DESK")},
        {"description": "City Sports Clinic invites Pia as a physio (sign in as Pia, then accept)", "email": "pia@example.com",
         "token": invite(api, clinic, chen, kind="PRACTITIONER", email="pia@example.com", disciplines=["PHYSIO"])},
    ]
    return {
        "password": DEMO_PASSWORD,
        "accounts": accounts,
        "organizations": {"IronWorks Gym": gym, "City Sports Clinic": clinic},
        "clients": {"Maya Patel": maya_client_id},
        "pending_invitations": pending,
    }


def main() -> None:
    if database_has_data():
        if "--reset" not in sys.argv:
            sys.exit("The dev database already has data. Run with --reset to empty identity and directory first.")
        empty_database()
    with TestClient(create_app()) as api:
        data = seed(api)
    SEED_FILE.write_text(json.dumps(data, indent=2))
    print(f"Seeded {len(data['accounts'])} accounts and 2 organizations. Wrote {SEED_FILE}.")
    for account in data["accounts"]:
        print(f"  {account['email']:<28} {account['summary']}")


if __name__ == "__main__":
    main()
