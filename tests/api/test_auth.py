import os

import pytest

pytestmark = pytest.mark.api

HAS_FIREBASE_AUTH_SECRETS = all(
    os.environ.get(var) for var in ("FIREBASE_API_KEY", "TEST_USER_EMAIL", "TEST_USER_PASSWORD")
)

def test_signup_creates_backend_user(api_context, firebase_id_token):
    response = api_context.post(
        "/api/auth/signup",
        data={
            "token": firebase_id_token,
            "name": "Playwright Test User",
            "nic": "200011200000",
            "contactNo": "0771234567",
            "email": os.environ["TEST_USER_EMAIL"],
            "address": "Test Address, Kandy",
        },
    )

    assert response.status == 200


@pytest.mark.smoke
@pytest.mark.skipif(
    not HAS_FIREBASE_AUTH_SECRETS,
    reason="Requires FIREBASE_API_KEY, TEST_USER_EMAIL, and TEST_USER_PASSWORD secrets",
)
def test_login_with_valid_firebase_token(api_context, firebase_id_token):
    response = api_context.post("/api/auth/login", data={"token": firebase_id_token})

    assert response.status == 200
    body = response.json()
    assert body["email"] == os.environ["TEST_USER_EMAIL"]
    assert body["userId"] is not None
    assert body["role"] is not None


@pytest.mark.smoke
def test_login_with_invalid_token_is_rejected(api_context):
    response = api_context.post("/api/auth/login", data={"token": "this-is-not-a-real-token"})

    assert response.status == 400
