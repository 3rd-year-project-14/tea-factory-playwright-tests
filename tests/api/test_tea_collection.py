import uuid
from datetime import date, datetime

import pytest

# This test simulates the full physical tea-collection chain:
#   supplier requests pickup -> driver's trip is linked to that request ->
#   driver logs bags picked up (trip-bags) -> inventory manager opens a
#   weighing session -> bag weights are recorded, which flips the trip-bag
# to "weighed".


@pytest.fixture
def test_supplier(db_conn):
    unique = uuid.uuid4().hex[:8]
    cur = db_conn.cursor()
    cur.execute(
        """
        INSERT INTO users (email, firebase_uid, name, nic, role, is_active, factory_id)
        VALUES (%s, %s, %s, %s, 'SUPPLIER', true, 1)
        RETURNING id
        """,
        (f"pw-collection-{unique}@test.com", f"pw-uid-col-{unique}", "PW Collection Supplier", f"PWC{unique}"),
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

    yield {"user_id": user_id, "supplier_id": supplier_id}

    cur = db_conn.cursor()
    cur.execute("DELETE FROM bag_weight WHERE supply_request_id IN (SELECT request_id FROM tea_supply_request WHERE supplier_id = %s)", (supplier_id,))
    cur.execute("DELETE FROM trip_bag WHERE supply_request_id IN (SELECT request_id FROM tea_supply_request WHERE supplier_id = %s)", (supplier_id,))
    cur.execute("DELETE FROM trip_supplier WHERE supply_request_id IN (SELECT request_id FROM tea_supply_request WHERE supplier_id = %s)", (supplier_id,))
    cur.execute("DELETE FROM tea_supply_request WHERE supplier_id = %s", (supplier_id,))
    cur.execute("DELETE FROM supplier WHERE supplier_id = %s", (supplier_id,))
    cur.execute("DELETE FROM weighing_session WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    cur.close()


@pytest.fixture
def trip_id(api_context):
    response = api_context.post("/api/trips", data={"driverId": 1, "routeId": 1})
    return response.json()["tripId"]


def test_full_collection_and_weighing_flow(api_context, test_supplier, trip_id):
    supplier_id = test_supplier["supplier_id"]

    # 1. Supplier requests a pickup
    request_response = api_context.post(
        "/api/tea-supply-requests", data={"supplierId": supplier_id, "estimatedBagCount": 1}
    )
    assert request_response.status == 200
    request_body = request_response.json()
    assert request_body["status"] == "pending"
    request_id = request_body["requestId"]

    # 2. That pickup request is linked to the driver's trip
    link_response = api_context.post(
        "/api/trip-suppliers", data={"tripId": trip_id, "supplyRequestId": request_id}
    )
    assert link_response.status == 200

    # 3. Bags exist for the route (generate a fresh batch so the number is guaranteed available)
    bags_response = api_context.post("/api/bags/generate", data={"routeId": 1, "quantity": 1})
    assert bags_response.status == 201
    bag_number = bags_response.json()["startBagNumber"]

    # 4. Driver logs the bag they picked up
    trip_bag_response = api_context.post(
        "/api/trip-bags",
        data={
            "tripId": trip_id,
            "supplyRequestId": request_id,
            "routeId": 1,
            "bagNumber": bag_number,
            "driverWeight": 25.5,
            "wet": False,
            "coarse": False,
            "type": "green",
            "note": "",
        },
    )
    assert trip_bag_response.status == 200
    trip_bag_id = trip_bag_response.json()["id"]

    # 5. Inventory manager opens a weighing session for the trip
    session_response = api_context.post(
        "/api/weighing-sessions",
        data={
            "tripId": trip_id,
            "sessionDate": str(date.today()),
            "userId": test_supplier["user_id"],
            "status": "in_progress",
        },
    )
    assert session_response.status == 200
    session_id = session_response.json()["sessionId"]

    # 6. The bag is weighed against that session
    weight_response = api_context.post(
        "/api/bagweights",
        data={
            "supplyRequestId": request_id,
            "sessionId": session_id,
            "bagNumbers": [bag_number],
            "grossWeight": 30.0,
            "tareWeight": 4.5,
            "netWeight": 25.5,
            "coarse": 0.0,
            "water": 0.0,
            "otherWeight": 0.0,
            "date": str(date.today()),
            "recordedAt": datetime.now().isoformat(),
            "reason": "",
        },
    )
    assert weight_response.status == 200
    assert weight_response.json()["bagTotal"] == 1

    # The recorded weighing should flip the trip-bag to "weighed"
    trip_bag_after = api_context.get(f"/api/trip-bags/{trip_bag_id}")
    assert trip_bag_after.status == 200
    assert trip_bag_after.json()["note"] == "weighed"


def test_tea_supply_request_requires_existing_supplier(api_context):
    response = api_context.post(
        "/api/tea-supply-requests", data={"supplierId": 999999, "estimatedBagCount": 1}
    )

    assert response.status == 500


def test_bag_generation_returns_sequential_range(api_context):
    response = api_context.post("/api/bags/generate", data={"routeId": 1, "quantity": 5})

    assert response.status == 201
    body = response.json()
    assert body["createdCount"] == 5
    assert body["routeId"] == 1
