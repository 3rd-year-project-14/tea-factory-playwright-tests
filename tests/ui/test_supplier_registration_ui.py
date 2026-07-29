import os
import uuid

import pytest
from playwright.sync_api import Page, expect

from conftest import FRONTEND_URL

# NOTE: There is no "Add Supplier" / registration form anywhere in the FactoryManager
# Suppliers UI -- SupplierRegister.jsx only ever renders the approve/reject table for
# requests that already exist (created via the supplier-facing /api/supplier-requests
# endpoint, which itself is blocked in this environment by the disabled Firebase Storage
# billing account -- see tests/api/test_supplier_request.py). So this test seeds a
# pending request directly in the DB (same pattern as test_supplier_request.py) and
# drives the part that's actually reachable from the FactoryManager UI: reviewing and
# approving a pending request.
#
# GAP FOUND (not fixed): /factoryManager/suppliers/pending and /suppliers/rejected are
# distinct routes but all three (plus the base /suppliers) render the exact same
# SupplierRegister component, whose `currentView` is local component state that always
# starts as "approved" -- it is never derived from the URL. So navigating straight to
# /suppliers/pending shows the *approved* (empty) table while the "Pending Requests"
# count card still correctly shows the real count. The only way to actually see the
# pending table is to click the "Pending Requests" summary card, which is what these
# tests do instead of relying on the dedicated URL.


@pytest.fixture
def as_factory_manager(db_conn):
    """FactoryManagerRoutes is only mounted in AppRouter when user.role === 'FACTORY_MANAGER'."""
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
def pending_supplier_request(db_conn):
    unique = uuid.uuid4().hex[:8]
    cur = db_conn.cursor()
    cur.execute(
        """
        INSERT INTO users (email, firebase_uid, name, nic, role, is_active)
        VALUES (%s, %s, %s, %s, 'PENDING_USER', true)
        RETURNING id
        """,
        (f"pw-supplier-ui-{unique}@test.com", f"pw-uid-ui-{unique}", "PW UI Supplier", f"PWUI{unique}"),
    )
    user_id = cur.fetchone()[0]

    cur.execute(
        """
        INSERT INTO supplier_request
            (user_id, factory_id, pickup_location, land_location, land_size, monthly_supply, status, requested_date)
        VALUES (%s, 1, 'Test Pickup, Kandy', 'Test Land, Kandy', 2.5, 100.0, 'pending', CURRENT_DATE)
        RETURNING id
        """,
        (user_id,),
    )
    request_id = cur.fetchone()[0]
    cur.close()

    yield {"request_id": request_id, "user_id": user_id, "name": "PW UI Supplier"}

    cur = db_conn.cursor()
    cur.execute("DELETE FROM supplier WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM supplier_request WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    cur.close()


def login(page: Page):
    page.goto(f"{FRONTEND_URL}/login")
    page.get_by_placeholder("Enter your email").fill(os.environ["TEST_USER_EMAIL"])
    page.get_by_placeholder("Enter your password").fill(os.environ["TEST_USER_PASSWORD"])
    page.get_by_role("button", name="Sign In").click()
    expect(page).not_to_have_url(f"{FRONTEND_URL}/login", timeout=10000)


def goto_pending_view(page: Page):
    page.goto(f"{FRONTEND_URL}/factoryManager/suppliers")
    page.get_by_text("Pending Requests").click()


def test_pending_request_appears_in_list(page: Page, as_factory_manager, pending_supplier_request):
    login(page)
    goto_pending_view(page)

    expect(page.get_by_text(pending_supplier_request["name"])).to_be_visible(timeout=10000)


def test_approving_request_via_ui_creates_active_supplier(
    page: Page, api_context, db_conn, as_factory_manager, pending_supplier_request
):
    login(page)
    goto_pending_view(page)

    expect(page.get_by_text(pending_supplier_request["name"])).to_be_visible(timeout=10000)
    # SupplierDetailsPage reads `currentView` from router location.state (defaulting
    # to "approved" if absent), so it must be reached by clicking through from the
    # pending list -- navigating straight to the URL would fetch it as an approved
    # supplier by this (nonexistent) supplier id and fail to load.
    page.get_by_title("View Details").click()
    expect(page).to_have_url(
        f"{FRONTEND_URL}/factoryManager/suppliers/{pending_supplier_request['request_id']}", timeout=10000
    )

    page.get_by_role("button", name="Approve").click()

    route_select = page.locator("select")
    expect(route_select).to_be_visible(timeout=10000)
    # ApprovalModal fetches routes asynchronously after opening -- the <select> is
    # visible immediately with only its "Select Route" placeholder option, so
    # selecting by index before the real options load would silently pick nothing.
    expect(route_select.locator("option")).not_to_have_count(1, timeout=10000)
    route_select.select_option(index=1)
    page.get_by_placeholder("e.g., 50").fill("10")
    page.get_by_role("button", name="Confirm Approval").click()

    page.wait_for_timeout(1000)

    # Approving deletes the supplier_request row entirely (SupplierService.
    # approveSupplierRequest calls supplierRequestRepo.delete(request) after creating
    # the Supplier row) rather than marking it "approved", so success is verified the
    # same way tests/api/test_supplier_request.py does: via the promoted user role and
    # the new supplier row, not via the (now-deleted) request.
    cur = db_conn.cursor()
    cur.execute("SELECT role FROM users WHERE id = %s", (pending_supplier_request["user_id"],))
    role = cur.fetchone()[0]
    cur.execute("SELECT is_active FROM supplier WHERE user_id = %s", (pending_supplier_request["user_id"],))
    is_active = cur.fetchone()[0]
    cur.close()

    assert role == "SUPPLIER"
    assert is_active is True

    requests = api_context.get(f"/api/supplier-requests?userId={pending_supplier_request['user_id']}").json()
    assert requests == []


def test_rejecting_request_via_ui_marks_it_rejected(
    page: Page, db_conn, as_factory_manager, pending_supplier_request
):
    login(page)
    goto_pending_view(page)
    expect(page.get_by_text(pending_supplier_request["name"])).to_be_visible(timeout=10000)
    page.get_by_title("View Details").click()
    expect(page).to_have_url(
        f"{FRONTEND_URL}/factoryManager/suppliers/{pending_supplier_request['request_id']}", timeout=10000
    )

    page.get_by_role("button", name="Reject").click()
    page.locator("textarea").fill("Playwright UI rejection reason")
    page.get_by_role("button", name="Confirm Rejection").click()

    page.wait_for_timeout(1000)

    # GAP FOUND (not fixed): GET /api/supplier-requests?userId= (used to verify the
    # approve case above too) returns full JPA entities including lazy Hibernate
    # associations, which Jackson can't serialize -- it 500s with "Type definition
    # error: ... ByteBuddyInterceptor" whenever the result is non-empty (confirmed by
    # querying it directly against a live pending row). Verifying via the DB instead,
    # same as tests/api/test_supplier_request.py::test_reject_supplier_request.
    cur = db_conn.cursor()
    cur.execute(
        "SELECT status, reject_reason FROM supplier_request WHERE id = %s",
        (pending_supplier_request["request_id"],),
    )
    status, reject_reason = cur.fetchone()
    cur.close()

    assert status == "rejected"
    assert reject_reason == "Playwright UI rejection reason"
