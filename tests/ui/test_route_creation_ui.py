import os
import uuid

import pytest
from playwright.sync_api import Page, expect

from conftest import FRONTEND_URL

# GAP FOUND (not fixed -- this is a frontend feature gap, out of this test's scope to
# implement): CreateRoute.jsx's Submit button is `type="button"` and its onClick handler
# only does `console.log(...)` -- it never calls the backend POST /api/routes endpoint,
# has no client-side validation, and shows no success/error feedback. This test proves
# that gap exists (submitting the form does NOT create a route via the API) so that if
# someone wires it up later without updating this test, the test starts failing and
# flags the change for review.


@pytest.fixture
def as_transport_manager(db_conn):
    """TransportManagerRoutes is only mounted in AppRouter when user.role ===
    'TRANSPORT_MANAGER', so the shared test user's role is temporarily elevated for
    this test and restored afterward."""
    cur = db_conn.cursor()
    cur.execute(
        "UPDATE users SET role = 'TRANSPORT_MANAGER', factory_id = 1 WHERE email = %s",
        (os.environ["TEST_USER_EMAIL"],),
    )
    cur.close()

    yield

    cur = db_conn.cursor()
    cur.execute(
        "UPDATE users SET role = 'PENDING_USER', factory_id = NULL WHERE email = %s",
        (os.environ["TEST_USER_EMAIL"],),
    )
    cur.close()


def login(page: Page):
    page.goto(f"{FRONTEND_URL}/login")
    page.get_by_placeholder("Enter your email").fill(os.environ["TEST_USER_EMAIL"])
    page.get_by_placeholder("Enter your password").fill(os.environ["TEST_USER_PASSWORD"])
    page.get_by_role("button", name="Sign In").click()
    expect(page).not_to_have_url(f"{FRONTEND_URL}/login", timeout=10000)


def test_route_creation_form_is_not_wired_to_backend(page: Page, api_context, as_transport_manager):
    route_name = f"PW UI Route {uuid.uuid4().hex[:8]}"

    before = api_context.get("/api/routes/factory/1").json()

    login(page)
    page.goto(f"{FRONTEND_URL}/transportManager/route/add")

    page.locator('input[name="routeName"]').fill(route_name)
    page.locator('input[name="startLocation"]').fill("Kandy")
    page.locator('input[name="endLocation"]').fill("Galle")
    page.locator('select[name="driverType"]').select_option(label="Private Driver")

    page.get_by_role("button", name="Submit").click()
    page.wait_for_timeout(500)

    after = api_context.get("/api/routes/factory/1").json()

    assert len(after) == len(before), (
        "Route count changed after submitting the Create Route form -- if this endpoint "
        "was just wired to the backend, update this test to assert the route was created "
        "and remove this gap-tracking assertion."
    )
    assert not any(r.get("name") == route_name for r in after)
