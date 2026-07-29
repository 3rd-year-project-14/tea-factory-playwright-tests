import os

import psycopg2
import pytest
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://localhost:8080"
FRONTEND_URL = "http://localhost:5174"
# tea-factory-mobile-app served via `expo start --web` (see metro.config.js there for
# the react-native-maps web stub required to make that build work at all). Must be
# started with BASE_URL=http://localhost:8080 so its API calls hit the same backend
# as everything else in this suite (its own .env defaults to a LAN IP for physical
# devices).
MOBILE_FRONTEND_URL = "http://localhost:8081"

FIREBASE_API_KEY = os.environ["FIREBASE_API_KEY"]
TEST_USER_EMAIL = os.environ["TEST_USER_EMAIL"]
TEST_USER_PASSWORD = os.environ["TEST_USER_PASSWORD"]

DB_CONFIG = dict(host="localhost", port=5432, dbname="Tea", user="postgres", password="1234")

# UI test playback speed: set SLOWMO_MS in .env (or the shell) to slow down browser
# actions so they're watchable in --headed mode, e.g. SLOWMO_MS=1000 for 1 second
# between actions. Defaults to 0 (full speed) if unset.
SLOWMO_MS = int(os.environ.get("SLOWMO_MS", "0"))


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    return {**browser_type_launch_args, "slow_mo": SLOWMO_MS}


@pytest.fixture
def db_conn():
    """Direct DB access, used only to set up/tear down test data that the API
    can't create yet (e.g. supplier-request creation is blocked by a disabled
    Firebase Storage billing account in this environment)."""
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def api_context(playwright):
    request_context = playwright.request.new_context(
        base_url=BASE_URL,
        extra_http_headers={"Content-Type": "application/json"},
    )
    yield request_context
    request_context.dispose()


@pytest.fixture(scope="session")
def api_context_multipart(playwright):
    """Separate context with no forced Content-Type, so Playwright can set its own
    multipart/form-data boundary header for file-upload / multipart endpoints."""
    request_context = playwright.request.new_context(base_url=BASE_URL)
    yield request_context
    request_context.dispose()


@pytest.fixture(scope="session")
def firebase_id_token():
    """Logs into the real Firebase project with the test user and returns a real ID token."""
    response = requests.post(
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword",
        params={"key": FIREBASE_API_KEY},
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "returnSecureToken": True,
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["idToken"]
