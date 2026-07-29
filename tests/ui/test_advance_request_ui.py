import os
import uuid

import pytest
from playwright.sync_api import Page, expect

from conftest import FRONTEND_URL


pytestmark = pytest.mark.ui

# Setup mirrors tests/api/test_advance_loan.py: an advance request needs an existing
# SUPPLIER row.
#
# NOTE on a discrepancy with tests/api/test_advance_loan.py: that file documents
# PUT /api/advances/{id}/approve (@PreAuthorize("hasRole('FACTORY_MANAGER')")) as
# always returning "Access Denied", reasoning that the Firebase auth filter is
# disabled so there's never an authenticated principal. Confirmed here that's only
# true for *unauthenticated* callers (bare curl/API calls with no token) -- a real
# browser session (this test, via a genuine Firebase login) attaches a valid ID
# token through the app's axios interceptor, and Spring Security does authorize it:
# approval succeeds end-to-end through the UI. So that "always denied" framing in
# the API test only holds for tests that don't attach a Firebase token to this
# specific call.


@pytest.fixture
def as_factory_manager(db_conn):
    cur = db_conn.cursor()
    cur.execute(
        "UPDATE users SET role = 'FACTORY_MANAGER', factory_id = 1 WHERE email = %s",
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


@pytest.fixture
def advance_supplier(db_conn):
    unique = uuid.uuid4().hex[:8]
    cur = db_conn.cursor()
    cur.execute(
        """
        INSERT INTO users (email, firebase_uid, name, nic, role, is_active, factory_id)
        VALUES (%s, %s, %s, %s, 'SUPPLIER', true, 1)
        RETURNING id
        """,
        (f"pw-adv-ui-{unique}@test.com", f"pw-uid-adv-ui-{unique}", "PW Advance UI Supplier", f"PWAU{unique}"),
    )
    user_id = cur.fetchone()[0]

    cur.execute(
        """
        INSERT INTO supplier (user_id, factory_id, route_id, pickup_location, land_location, land_size,
                                approved_date, is_active, initial_bag_count)
        VALUES (%s, 1, 1, 'Test Pickup', 'Test Land', 2.0, CURRENT_DATE, true, 5)
        RETURNING supplier_id
        """,
        (user_id,),
    )
    supplier_id = cur.fetchone()[0]
    cur.close()

    yield supplier_id

    cur = db_conn.cursor()
    cur.execute("DELETE FROM supplier_payments WHERE supplier_id = %s", (supplier_id,))
    cur.execute("DELETE FROM supplier_advances WHERE supplier_id = %s", (supplier_id,))
    cur.execute("DELETE FROM supplier WHERE supplier_id = %s", (supplier_id,))
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    cur.close()


@pytest.fixture
def requested_advance(api_context, advance_supplier):
    response = api_context.post(
        "/api/advances/request",
        data={"supplierId": advance_supplier, "requestedAmount": 5000, "purpose": "PW UI test", "paymentMethod": "CASH"},
    )
    return response.json()["id"]


def login(page: Page):
    page.goto(f"{FRONTEND_URL}/login")
    page.get_by_placeholder("Enter your email").fill(os.environ["TEST_USER_EMAIL"])
    page.get_by_placeholder("Enter your password").fill(os.environ["TEST_USER_PASSWORD"])
    page.get_by_role("button", name="Sign In").click()
    expect(page).not_to_have_url(f"{FRONTEND_URL}/login", timeout=10000)


def goto_advance_detail(page: Page, advance_id):
    # AdvanceDetails.jsx fetches its data in a useEffect on mount -- on a cold
    # `page.goto` straight to this deep link, that effect occasionally doesn't fire
    # before the initial render settles (same class of flake as
    # test_payment_processing_ui.py's adhoc-queue fetch). A single reload fixes it.
    page.goto(f"{FRONTEND_URL}/factoryManager/payment/advance/{advance_id}")
    try:
        expect(page.get_by_role("button", name="Approve")).to_be_visible(timeout=5000)
    except AssertionError:
        page.reload()
        expect(page.get_by_role("button", name="Approve")).to_be_visible(timeout=10000)


def test_rejecting_advance_via_ui_updates_status(
    page: Page, api_context, as_factory_manager, requested_advance
):
    login(page)
    goto_advance_detail(page, requested_advance)

    page.get_by_role("button", name="Reject").click()
    page.locator("textarea").fill("Playwright UI rejection")
    page.get_by_role("button", name="Confirm Rejection").click()

    expect(page).to_have_url(f"{FRONTEND_URL}/factoryManager/payment/advance", timeout=10000)

    detail = api_context.get(f"/api/advances/{requested_advance}").json()
    assert detail["status"] == "REJECTED"
    assert detail["rejectionReason"] == "Playwright UI rejection"


def test_approving_advance_via_ui_updates_status(
    page: Page, api_context, as_factory_manager, requested_advance
):
    login(page)
    goto_advance_detail(page, requested_advance)

    page.get_by_role("button", name="Approve").click()
    page.get_by_role("button", name="Confirm Approval").click()

    expect(page).to_have_url(f"{FRONTEND_URL}/factoryManager/payment/advance", timeout=10000)

    detail = api_context.get(f"/api/advances/{requested_advance}").json()
    assert detail["status"] == "APPROVED"
    assert detail["approvedAmount"] == 5000
