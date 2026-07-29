import uuid

import pytest


pytestmark = pytest.mark.api


# NOTE: POST /api/supplier-requests (creating a request) uploads the NIC image to
# Firebase Storage, and that project's billing account is currently disabled, so the
# real create endpoint returns 500 regardless of payload. These tests set up the
# supplier_request row directly in the DB instead, so the approve/reject endpoints
# themselves (the part we actually own/can fix) are still verified end-to-end.


@pytest.fixture
def pending_user(db_conn):
    unique = uuid.uuid4().hex[:8]
    cur = db_conn.cursor()
    cur.execute(
        """
        INSERT INTO users (email, firebase_uid, name, nic, role, is_active)
        VALUES (%s, %s, %s, %s, 'PENDING_USER', true)
        RETURNING id
        """,
        (f"pw-supplier-{unique}@test.com", f"pw-uid-{unique}", "PW Supplier", f"PW{unique}"),
    )
    user_id = cur.fetchone()[0]
    cur.close()

    yield user_id

    cur = db_conn.cursor()
    cur.execute("DELETE FROM supplier WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM supplier_request WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    cur.close()


@pytest.fixture
def pending_supplier_request(db_conn, pending_user):
    cur = db_conn.cursor()
    cur.execute(
        """
        INSERT INTO supplier_request
            (user_id, factory_id, pickup_location, land_location, land_size, monthly_supply, status, requested_date)
        VALUES (%s, 1, 'Test Pickup, Kandy', 'Test Land, Kandy', 2.5, 100.0, 'pending', CURRENT_DATE)
        RETURNING id
        """,
        (pending_user,),
    )
    request_id = cur.fetchone()[0]
    cur.close()
    return request_id


def test_duplicate_supplier_request_is_rejected(db_conn, pending_supplier_request, pending_user):
    """Same user_id has a unique constraint on supplier_request -> DB enforces one request per user."""
    cur = db_conn.cursor()
    with pytest.raises(Exception):
        cur.execute(
            """
            INSERT INTO supplier_request (user_id, factory_id, pickup_location, status, requested_date)
            VALUES (%s, 1, 'Second Attempt', 'pending', CURRENT_DATE)
            """,
            (pending_user,),
        )
    cur.close()


def test_approve_supplier_request_promotes_user_to_supplier(api_context, db_conn, pending_supplier_request, pending_user):
    response = api_context.post(
        f"/api/supplier-requests/{pending_supplier_request}/approve",
        data={"routeId": 1, "initialBagCount": 5},
    )

    assert response.status == 200

    cur = db_conn.cursor()
    cur.execute("SELECT role FROM users WHERE id = %s", (pending_user,))
    role = cur.fetchone()[0]
    cur.execute("SELECT is_active, initial_bag_count FROM supplier WHERE user_id = %s", (pending_user,))
    is_active, initial_bag_count = cur.fetchone()
    cur.close()

    assert role == "SUPPLIER"
    assert is_active is True
    assert initial_bag_count == 5


def test_approve_supplier_request_with_missing_route_fails(api_context, pending_supplier_request):
    response = api_context.post(
        f"/api/supplier-requests/{pending_supplier_request}/approve",
        data={"routeId": 999999, "initialBagCount": 5},
    )

    assert response.status == 404


def test_reject_supplier_request(api_context, db_conn, pending_supplier_request, pending_user):
    response = api_context.post(
        f"/api/supplier-requests/{pending_supplier_request}/reject",
        data={"reason": "Land size too small"},
    )

    assert response.status == 200

    cur = db_conn.cursor()
    cur.execute("SELECT status, reject_reason FROM supplier_request WHERE id = %s", (pending_supplier_request,))
    status, reject_reason = cur.fetchone()
    cur.close()

    assert status == "rejected"
    assert reject_reason == "Land size too small"
