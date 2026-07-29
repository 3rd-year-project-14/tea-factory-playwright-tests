import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest

# End-to-end payment calculation flow:
#   1. A supplier has bag_weight records (net weight) recorded for a month
#      (built the same way as the flow #4 tea-collection chain).
#   2. An OWNER/PAYMENT_MANAGER sets a tea rate for that month and approves it.
#   3. POST /api/payments/monthly/calculate reads the approved rate and sums
#      each active supplier's net weight for the month, and computes
#      grossAmount = totalWeight * finalRatePerKg.


@pytest.fixture
def paid_supplier(db_conn):
    """A SUPPLIER with an approved bag-weight record recorded for the current month."""
    unique = uuid.uuid4().hex[:8]
    cur = db_conn.cursor()

    cur.execute(
        """
        INSERT INTO users (email, firebase_uid, name, nic, role, is_active, factory_id)
        VALUES (%s, %s, %s, %s, 'SUPPLIER', true, 1)
        RETURNING id
        """,
        (f"pw-payment-{unique}@test.com", f"pw-uid-pay-{unique}", "PW Payment Supplier", f"PWP{unique}"),
    )
    user_id = cur.fetchone()[0]

    cur.execute(
        """
        INSERT INTO supplier (user_id, factory_id, route_id, pickup_location, land_location, land_size,
                                approved_date, is_active, initial_bag_count, payment_method_preference)
        VALUES (%s, 1, 1, 'Test Pickup', 'Test Land', 2.0, CURRENT_DATE, true, 5, 'CASH')
        RETURNING supplier_id
        """,
        (user_id,),
    )
    supplier_id = cur.fetchone()[0]

    cur.execute(
        """
        INSERT INTO tea_supply_request (supplier_id, supply_date, estimated_bag_count, status)
        VALUES (%s, CURRENT_DATE, 1, 'collected')
        RETURNING request_id
        """,
        (supplier_id,),
    )
    request_id = cur.fetchone()[0]

    cur.execute(
        """
        INSERT INTO weighing_session (trip_id, session_date, user_id, status)
        SELECT trip_id, CURRENT_DATE, %s, 'completed' FROM trip LIMIT 1
        RETURNING session_id
        """,
        (user_id,),
    )
    session_id = cur.fetchone()[0]

    net_weight = Decimal("25.50")
    cur.execute(
        """
        INSERT INTO bag_weight (bag_total, coarse, date, gross_weight, net_weight, other_weight,
                                  reason, recorded_at, tare_weight, water, supply_request_id, session_id)
        VALUES (1, 0, CURRENT_DATE, 30.0, %s, 0, '', %s, 4.5, 0, %s, %s)
        """,
        (net_weight, datetime.now(), request_id, session_id),
    )
    cur.close()

    yield {"user_id": user_id, "supplier_id": supplier_id, "net_weight": net_weight}

    cur = db_conn.cursor()
    cur.execute("DELETE FROM payment_audit_log WHERE payment_id IN (SELECT id FROM payments WHERE supplier_id = %s)", (str(supplier_id),))
    cur.execute("DELETE FROM payment_deductions WHERE monthly_payment_id IN (SELECT id FROM payments WHERE supplier_id = %s)", (str(supplier_id),))
    cur.execute("DELETE FROM payments WHERE supplier_id = %s", (str(supplier_id),))
    cur.execute("DELETE FROM bag_weight WHERE supply_request_id = %s", (request_id,))
    cur.execute("DELETE FROM weighing_session WHERE session_id = %s", (session_id,))
    cur.execute("DELETE FROM tea_supply_request WHERE request_id = %s", (request_id,))
    cur.execute("DELETE FROM supplier WHERE supplier_id = %s", (supplier_id,))
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    cur.close()


@pytest.fixture
def approved_tea_rate(api_context, db_conn, paid_supplier):
    """Creates a tea rate for the current month and approves it."""
    month_str = date.today().strftime("%Y-%m")
    rate_per_kg = Decimal("250.00")

    create_response = api_context.post(
        "/api/tea_rates",
        data={
            "userId": paid_supplier["user_id"],
            "month": month_str,
            "nsa": 100,
            "gsa": 100,
            "monthlyRate": float(rate_per_kg),
            "totalWeight": 0,
            "finalRatePerKg": float(rate_per_kg),
            "totalPayout": 0,
        },
    )
    assert create_response.status == 200

    pending = api_context.get("/api/tea_rates/pending").json()
    created = next(r for r in pending if r["month"] == month_str)
    rate_id = created["teaRateId"]

    approve_response = api_context.put(f"/api/tea_rates/{rate_id}/approve")
    assert approve_response.status == 200

    yield {"rate_id": rate_id, "rate_per_kg": rate_per_kg, "month": month_str}

    cur = db_conn.cursor()
    cur.execute("DELETE FROM tea_rate WHERE tea_rate_id = %s", (rate_id,))
    cur.close()


def test_monthly_payment_calculation_matches_weight_times_rate(api_context, paid_supplier, approved_tea_rate):
    today = date.today()

    response = api_context.post(
        "/api/payments/monthly/calculate",
        data={"month": today.month, "year": today.year, "factoryId": "1"},
    )

    assert response.status == 200
    payments = response.json()
    payment = next(p for p in payments if p["supplierId"] == str(paid_supplier["supplier_id"]))

    expected_gross = float(paid_supplier["net_weight"]) * float(approved_tea_rate["rate_per_kg"])
    assert payment["grossAmount"] == pytest.approx(expected_gross)
    assert payment["totalWeight"] == pytest.approx(float(paid_supplier["net_weight"]))
    assert payment["status"] == "CALCULATED"


def test_calculate_without_approved_rate_fails(api_context, paid_supplier, db_conn):
    """No tea rate has been approved for next month -> calculation should fail."""
    next_month_date = date.today().replace(day=1)
    next_month = next_month_date.month % 12 + 1
    next_year = next_month_date.year + (1 if next_month_date.month == 12 else 0)

    response = api_context.post(
        "/api/payments/monthly/calculate",
        data={"month": next_month, "year": next_year, "factoryId": "1"},
    )

    assert response.status in (400, 500)


def test_calculate_with_invalid_factory_id_fails(api_context):
    today = date.today()

    response = api_context.post(
        "/api/payments/monthly/calculate",
        data={"month": today.month, "year": today.year, "factoryId": "not-a-number"},
    )

    assert response.status in (400, 500)
