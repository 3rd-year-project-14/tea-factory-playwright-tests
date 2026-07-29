import uuid

import pytest


pytestmark = pytest.mark.api

# Advance and loan-request flows share one prerequisite: an existing SUPPLIER.
# NOTE: the advance /approve endpoint is annotated @PreAuthorize("hasRole('FACTORY_MANAGER')").
# Because the Firebase auth filter is disabled in this environment (SecurityConfig permits
# all HTTP requests), there is never an authenticated principal in the SecurityContext, so
# this specific endpoint always returns "Access Denied" regardless of who calls it -- a
# genuine environment limitation (like the NIC-image Firebase Storage billing issue), not
# something these tests work around. It's covered as a documented negative case below.
# The /reject and /pay endpoints have no such guard, so the REQUESTED -> REJECTED and
# REQUESTED -> PAID transitions (the ones this codebase actually lets you drive end-to-end)
# are tested directly.


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
        (f"pw-loan-{unique}@test.com", f"pw-uid-loan-{unique}", "PW Loan Supplier", f"PWL{unique}"),
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
    cur.execute("DELETE FROM loan WHERE supplier_id = %s", (supplier_id,))
    cur.execute("DELETE FROM loan_request WHERE supplier_id = %s", (supplier_id,))
    cur.execute("DELETE FROM supplier_advances WHERE supplier_id = %s", (supplier_id,))
    cur.execute("DELETE FROM supplier WHERE supplier_id = %s", (supplier_id,))
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    cur.close()


def test_create_advance_request(api_context, advance_supplier):
    response = api_context.post(
        "/api/advances/request",
        data={"supplierId": advance_supplier, "requestedAmount": 5000, "purpose": "Emergency", "paymentMethod": "CASH"},
    )

    assert response.status == 201
    body = response.json()
    assert body["status"] == "REQUESTED"
    assert body["requestedAmount"] == 5000


def test_advance_request_over_eligibility_limit_is_rejected(api_context, advance_supplier):
    response = api_context.post(
        "/api/advances/request",
        data={"supplierId": advance_supplier, "requestedAmount": 150000, "purpose": "Too much", "paymentMethod": "CASH"},
    )

    assert response.status == 400


def test_advance_approve_endpoint_is_locked_by_disabled_auth(api_context, advance_supplier):
    """Documents the current environment limitation: @PreAuthorize with no auth filter
    always denies, so this endpoint cannot be exercised end-to-end here."""
    create_response = api_context.post(
        "/api/advances/request",
        data={"supplierId": advance_supplier, "requestedAmount": 4000, "purpose": "Test", "paymentMethod": "CASH"},
    )
    advance_id = create_response.json()["id"]

    response = api_context.put(
        f"/api/advances/{advance_id}/approve",
        data={"approvedByUserId": advance_supplier, "approvedAmount": 4000, "action": "APPROVE"},
    )

    assert response.status == 500
    assert "Access Denied" in response.json()["message"]


def test_advance_reject_flow(api_context, advance_supplier):
    create_response = api_context.post(
        "/api/advances/request",
        data={"supplierId": advance_supplier, "requestedAmount": 3000, "purpose": "Test reject", "paymentMethod": "CASH"},
    )
    advance_id = create_response.json()["id"]

    response = api_context.put(
        f"/api/advances/{advance_id}/reject",
        data={"rejectedByUserId": advance_supplier, "rejectionReason": "Not eligible"},
    )

    assert response.status == 200
    body = response.json()
    assert body["status"] == "REJECTED"
    assert body["rejectionReason"] == "Not eligible"


def test_advance_reject_twice_fails(api_context, advance_supplier):
    create_response = api_context.post(
        "/api/advances/request",
        data={"supplierId": advance_supplier, "requestedAmount": 3000, "purpose": "Test", "paymentMethod": "CASH"},
    )
    advance_id = create_response.json()["id"]

    first = api_context.put(
        f"/api/advances/{advance_id}/reject",
        data={"rejectedByUserId": advance_supplier, "rejectionReason": "First"},
    )
    assert first.status == 200

    second = api_context.put(
        f"/api/advances/{advance_id}/reject",
        data={"rejectedByUserId": advance_supplier, "rejectionReason": "Second"},
    )
    assert second.status == 500


def test_advance_mark_as_paid(api_context, advance_supplier):
    create_response = api_context.post(
        "/api/advances/request",
        data={"supplierId": advance_supplier, "requestedAmount": 2000, "purpose": "Test pay", "paymentMethod": "CASH"},
    )
    advance_id = create_response.json()["id"]

    response = api_context.put(f"/api/advances/{advance_id}/pay")

    assert response.status == 200
    assert response.json()["status"] == "PAID"


@pytest.fixture
def active_loan_rate(api_context):
    """Not cleaned up: any loan created against this rate (in the same test) is deleted
    first via the advance_supplier fixture teardown, and rates have no uniqueness
    constraint that would make leftover rows a problem for future test runs."""
    response = api_context.post(
        "/api/loan-rate", data={"rate": 5, "effectiveDate": "2026-01-01", "status": True}
    )
    assert response.status == 200
    return response.json()["rateId"]


def test_loan_request_approval_creates_loan_with_correct_instalment(api_context, advance_supplier, active_loan_rate):
    request_response = api_context.post(
        "/api/loan-requests", data={"supplierId": advance_supplier, "amount": 10000, "months": 6}
    )
    assert request_response.status == 200
    req_id = request_response.json()["reqId"]
    assert request_response.json()["status"] == "PENDING"

    approve_response = api_context.put(f"/api/loan-requests/{req_id}/approve")
    assert approve_response.status == 200

    loans = api_context.get(f"/api/loans/supplier/{advance_supplier}").json()
    loan = next(l for l in loans if l["loanId"] is not None)

    expected_total = 10000 * 1.05
    expected_instalment = expected_total / 6
    assert float(loan["remainingAmount"]) == pytest.approx(expected_total)
    assert float(loan["monthlyInstalment"]) == pytest.approx(expected_instalment, abs=0.01)
    assert loan["status"] == "REMAINING"


def test_loan_request_approve_twice_fails(api_context, advance_supplier, active_loan_rate):
    request_response = api_context.post(
        "/api/loan-requests", data={"supplierId": advance_supplier, "amount": 5000, "months": 3}
    )
    req_id = request_response.json()["reqId"]

    first = api_context.put(f"/api/loan-requests/{req_id}/approve")
    assert first.status == 200

    second = api_context.put(f"/api/loan-requests/{req_id}/approve")
    assert second.status == 400
