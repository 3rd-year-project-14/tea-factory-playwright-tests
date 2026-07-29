import os
import uuid
from decimal import Decimal

import pytest
from playwright.sync_api import Page, expect

from conftest import FRONTEND_URL

# GAP FOUND (not fixed -- out of scope for this test to implement): the "Adhoc"
# payment approval screen (PaymentManager/PaymentProceed/AdhocPaymentProcessing.jsx,
# mounted at /factoryManager/payment/proceed/adhoc) filters the payments it fetches by
#   payment.paymentMethod === "BANK" / "CASH"
# but the API's PaymentDTO field is actually `disbursementMethod` (confirmed via
# GET /api/payments/adhoc/pending, which returns real rows with
# "disbursementMethod": "CASH" and no "paymentMethod" key at all). Both the bank and
# cash filters are therefore always empty arrays -- this screen can never display a
# single payment, no matter how much real approved-adhoc data exists for the factory.
# This is a separate, more fundamental bug than the "Add to Collection Queue" button's
# broken approveAdhocPayment call signature (api/paymentManager.js's helper takes two
# positional args but is called with one object) -- that second bug is simply
# unreachable through the UI because no row ever renders to click.
#
# Both tests below seed a real APPROVED adhoc-eligible payment via direct DB insert
# (mirroring tests/api/test_advance_loan.py's supplier-seeding pattern) and confirm via
# the API that the data genuinely exists, then assert the UI shows "0 Payments"
# anyway.


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
def approved_adhoc_payment(db_conn):
    """getPendingAdhocPayments actually queries status=APPROVED payments of type
    LOAN/ADVANCE/FERTILIZER whose supplier belongs to the requested factory -- despite
    the "pending" naming, these are payments approved elsewhere and now awaiting
    disbursement collection. Reuses the supplier-seeding pattern from
    tests/api/test_advance_loan.py."""
    unique = uuid.uuid4().hex[:8]
    cur = db_conn.cursor()
    cur.execute(
        """
        INSERT INTO users (email, firebase_uid, name, nic, role, is_active, factory_id)
        VALUES (%s, %s, %s, %s, 'SUPPLIER', true, 1)
        RETURNING id
        """,
        (f"pw-adhoc-{unique}@test.com", f"pw-uid-adhoc-{unique}", "PW Adhoc Supplier", f"PWA{unique}"),
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

    payment_id = f"PW-ADHOC-{unique.upper()}"
    net_amount = Decimal("2500.00")
    cur.execute(
        """
        INSERT INTO payments (id, payment_type, supplier_id, route_id, period_month, period_year,
          gross_amount, total_weight, tea_rate, deduction_amount, net_amount, disbursement_method,
          status, approved_at, created_at, updated_at)
        VALUES (%s, 'ADVANCE', %s, '1', 7, 2026, %s, 0, 0, 0, %s, 'CASH', 'APPROVED', now(), now(), now())
        """,
        (payment_id, str(supplier_id), net_amount, net_amount),
    )
    cur.close()

    yield {"payment_id": payment_id, "supplier_id": supplier_id, "user_id": user_id}

    cur = db_conn.cursor()
    cur.execute("DELETE FROM payment_audit_log WHERE payment_id = %s", (payment_id,))
    cur.execute("DELETE FROM payments WHERE id = %s", (payment_id,))
    cur.execute("DELETE FROM supplier WHERE supplier_id = %s", (supplier_id,))
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    cur.close()


def login(page: Page):
    page.goto(f"{FRONTEND_URL}/login")
    page.get_by_placeholder("Enter your email").fill(os.environ["TEST_USER_EMAIL"])
    page.get_by_placeholder("Enter your password").fill(os.environ["TEST_USER_PASSWORD"])
    page.get_by_role("button", name="Sign In").click()
    expect(page).not_to_have_url(f"{FRONTEND_URL}/login", timeout=10000)


def goto_adhoc_page(page: Page):
    # AdhocPaymentProcessing.jsx fetches its data in a useEffect on mount -- on a cold
    # `page.goto` straight to this deep link, that effect can occasionally fire before
    # the route/layout has fully settled. A single reload guards against that class of
    # flake; it does not affect the field-name bug documented above.
    page.goto(f"{FRONTEND_URL}/factoryManager/payment/proceed/adhoc")
    expect(page.get_by_text("Ad-hoc Payment Processing")).to_be_visible(timeout=10000)
    page.reload()
    expect(page.get_by_text("Ad-hoc Payment Processing")).to_be_visible(timeout=10000)


def test_approved_adhoc_payment_never_renders_due_to_field_name_mismatch(
    page: Page, api_context, as_factory_manager, approved_adhoc_payment
):
    login(page)

    pending = api_context.get("/api/payments/adhoc/pending", params={"factoryId": "1"}).json()
    assert any(p["id"] == approved_adhoc_payment["payment_id"] for p in pending), (
        "Seeded payment isn't even visible via the API -- fixture setup is broken, "
        "not the page under test."
    )

    goto_adhoc_page(page)

    expect(page.get_by_text("Rs. 2,500.00")).not_to_be_visible()
    expect(page.get_by_text("0 Payments").first).to_be_visible()
