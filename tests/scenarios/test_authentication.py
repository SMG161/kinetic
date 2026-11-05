"""Brief, build target 1: people sign in, and the system knows who they are.
Nothing trusts a client-supplied claim about identity."""

from datetime import timedelta

from fastapi.testclient import TestClient

from kinetic.shared_kernel import FixedClock

MAYA = {"full_name": "Maya Patel", "email": "maya@example.com", "password": "correct horse battery"}


def signup(client: TestClient, **overrides: str) -> dict:
    response = client.post("/auth/signup", json=MAYA | overrides)
    assert response.status_code == 201, response.text
    return response.json()


def bearer(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


class TestSignup:
    def test_signup_signs_you_in_and_me_knows_who_you_are(self, client):
        tokens = signup(client)
        me = client.get("/me", headers=bearer(tokens))
        assert me.status_code == 200
        assert me.json()["full_name"] == "Maya Patel"
        assert me.json()["email"] == "maya@example.com"

    def test_email_is_taken_regardless_of_case(self, client):
        signup(client)
        response = client.post("/auth/signup", json=MAYA | {"email": "MAYA@Example.com"})
        assert response.status_code == 409

    def test_rejects_weak_password_and_malformed_email(self, client):
        assert client.post("/auth/signup", json=MAYA | {"password": "short"}).status_code == 422
        assert client.post("/auth/signup", json=MAYA | {"email": "not-an-email"}).status_code == 422
        assert client.post("/auth/signup", json=MAYA | {"password": "x" * 129}).status_code == 422

    def test_a_failed_signup_leaves_nothing_behind(self, client):
        client.post("/auth/signup", json=MAYA | {"password": "short"})
        assert client.post("/auth/login", json={"email": MAYA["email"], "password": "short"}).status_code == 401
        signup(client)  # the email is still free


class TestLogin:
    def test_login_with_the_right_password(self, client):
        signup(client)
        response = client.post("/auth/login", json={"email": "Maya@Example.com", "password": MAYA["password"]})
        assert response.status_code == 200
        assert client.get("/me", headers=bearer(response.json())).status_code == 200

    def test_wrong_password_and_unknown_email_look_the_same(self, client):
        signup(client)
        wrong_password = client.post("/auth/login", json={"email": MAYA["email"], "password": "nope nope nope"})
        unknown_email = client.post("/auth/login", json={"email": "ghost@example.com", "password": "nope nope nope"})
        assert wrong_password.status_code == unknown_email.status_code == 401
        assert wrong_password.json() == unknown_email.json()


class TestAccessToken:
    def test_me_requires_a_token(self, client):
        response = client.get("/me")
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"

    def test_me_rejects_a_forged_token(self, client):
        assert client.get("/me", headers={"Authorization": "Bearer not.a.jwt"}).status_code == 401

    def test_access_token_expires_after_fifteen_minutes(self, client, clock: FixedClock):
        tokens = signup(client)
        clock.advance(timedelta(minutes=14, seconds=59))
        assert client.get("/me", headers=bearer(tokens)).status_code == 200
        clock.advance(timedelta(seconds=1))
        assert client.get("/me", headers=bearer(tokens)).status_code == 401


class TestRefresh:
    def test_refresh_issues_a_working_access_token(self, client, clock: FixedClock):
        tokens = signup(client)
        clock.advance(timedelta(minutes=20))
        refreshed = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert refreshed.status_code == 200
        assert client.get("/me", headers=bearer(refreshed.json())).status_code == 200

    def test_each_refresh_token_works_once(self, client):
        tokens = signup(client)
        assert client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 200
        assert client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401

    def test_refresh_token_expires_after_thirty_days(self, client, clock: FixedClock):
        tokens = signup(client)
        clock.advance(timedelta(days=30))
        assert client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401


class TestLogout:
    def test_logout_stops_refresh_and_the_access_token_dies_at_expiry(self, client, clock: FixedClock):
        tokens = signup(client)
        assert client.post("/auth/logout", headers=bearer(tokens)).status_code == 204
        assert client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
        # The accepted trade-off: an issued JWT is not revoked, it lives out its 15 minutes.
        assert client.get("/me", headers=bearer(tokens)).status_code == 200
        clock.advance(timedelta(minutes=15))
        assert client.get("/me", headers=bearer(tokens)).status_code == 401

    def test_logout_on_one_device_keeps_the_other_signed_in(self, client):
        signup(client)
        phone = client.post("/auth/login", json={"email": MAYA["email"], "password": MAYA["password"]}).json()
        laptop = client.post("/auth/login", json={"email": MAYA["email"], "password": MAYA["password"]}).json()
        client.post("/auth/logout", headers=bearer(phone))
        assert client.post("/auth/refresh", json={"refresh_token": laptop["refresh_token"]}).status_code == 200
