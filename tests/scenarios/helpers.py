"""Small HTTP helpers shared by scenario tests."""

from fastapi.testclient import TestClient

PASSWORD = "correct horse battery"


def signup(client: TestClient, full_name: str, email: str, password: str = PASSWORD) -> dict:
    response = client.post("/auth/signup", json={"full_name": full_name, "email": email, "password": password})
    assert response.status_code == 201, response.text
    return response.json()


def login(client: TestClient, email: str, password: str = PASSWORD) -> dict:
    """Sign in again, e.g. after moving the clock past the 15-minute access token."""
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return bearer(response.json())


def bearer(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}
