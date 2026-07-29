import uuid
from datetime import date

import os
import pytest
from playwright.sync_api import Page, expect

from conftest import FRONTEND_URL

# Mirrors the setup chain in tests/api/test_tea_collection.py: supplier -> pickup
# request -> trip-supplier link -> a bag generated and logged by the driver -> a
# weighing session opened for the trip. The UI page under test
# (InventoryManager/LeafWeight/leaf_bags_weight.jsx) is the "Bag Weighing Entry" screen
# reached at /inventoryManager/leaf_weight/route/:tripId/supplier/:supplyRequestId.


@pytest.fixture
def as_inventory_manager(db_conn):
    """InventoryManagerRoutes is only mounted in AppRouter when user.role === 'INVENTORY_MANAGER'."""
    cur = db_conn.cursor()
    cur.execute(
        "UPDATE users SET role = 'INVENTORY_MANAGER', factory_id = 1 WHERE email = %s",
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
def test_supplier(db_conn):
    unique = uuid.uuid4().hex[:8]
    cur = db_conn.cursor()
    cur.execute(
        """
        INSERT INTO users (email, firebase_uid, name, nic, role, is_active, factory_id)
        VALUES (%s, %s, %s, %s, 'SUPPLIER', true, 1)
        RETURNING id
        """,
        (f"pw-weigh-ui-{unique}@test.com", f"pw-uid-weigh-ui-{unique}", "PW Weighing UI Supplier", f"PWW{unique}"),
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
    cur.execute(
        "DELETE FROM bag_weight WHERE supply_request_id IN (SELECT request_id FROM tea_supply_request WHERE supplier_id = %s)",
        (supplier_id,),
    )
    cur.execute(
        "DELETE FROM trip_bag WHERE supply_request_id IN (SELECT request_id FROM tea_supply_request WHERE supplier_id = %s)",
        (supplier_id,),
    )
    cur.execute(
        "DELETE FROM trip_supplier WHERE supply_request_id IN (SELECT request_id FROM tea_supply_request WHERE supplier_id = %s)",
        (supplier_id,),
    )
    cur.execute("DELETE FROM tea_supply_request WHERE supplier_id = %s", (supplier_id,))
    cur.execute("DELETE FROM supplier WHERE supplier_id = %s", (supplier_id,))
    cur.execute("DELETE FROM weighing_session WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    cur.close()


@pytest.fixture
def trip_id(api_context):
    response = api_context.post("/api/trips", data={"driverId": 1, "routeId": 1})
    return response.json()["tripId"]


@pytest.fixture
def bag_ready_to_weigh(api_context, test_supplier, trip_id):
    supplier_id = test_supplier["supplier_id"]

    request_response = api_context.post(
        "/api/tea-supply-requests", data={"supplierId": supplier_id, "estimatedBagCount": 1}
    )
    request_id = request_response.json()["requestId"]

    api_context.post("/api/trip-suppliers", data={"tripId": trip_id, "supplyRequestId": request_id})

    bag_number = api_context.post("/api/bags/generate", data={"routeId": 1, "quantity": 1}).json()["startBagNumber"]

    api_context.post(
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

    api_context.post(
        "/api/weighing-sessions",
        data={
            "tripId": trip_id,
            "sessionDate": str(date.today()),
            "userId": test_supplier["user_id"],
            "status": "in_progress",
        },
    )

    return {"request_id": request_id, "bag_number": bag_number}


def login(page: Page):
    page.goto(f"{FRONTEND_URL}/login")
    page.get_by_placeholder("Enter your email").fill(os.environ["TEST_USER_EMAIL"])
    page.get_by_placeholder("Enter your password").fill(os.environ["TEST_USER_PASSWORD"])
    page.get_by_role("button", name="Sign In").click()
    expect(page).not_to_have_url(f"{FRONTEND_URL}/login", timeout=10000)


def test_recording_bag_weight_via_ui_persists_via_api(
    page: Page, api_context, as_inventory_manager, bag_ready_to_weigh, trip_id
):
    login(page)
    page.goto(f"{FRONTEND_URL}/inventoryManager/leaf_weight/route/{trip_id}/supplier/{bag_ready_to_weigh['request_id']}")

    expect(page.get_by_text("Bag Weight Management")).to_be_visible(timeout=10000)

    page.locator("#bagSearch").fill(str(bag_ready_to_weigh["bag_number"]))
    # Row 0's checkbox is the "select all" header checkbox; after filtering to a single
    # matching bag, row 1 is the only data row's checkbox.
    page.locator('input[type="checkbox"]').nth(1).check()

    page.get_by_placeholder("Enter weight...").fill("30")

    enter_button = page.get_by_role("button", name="Enter")
    expect(enter_button).to_be_enabled()
    enter_button.click()

    page.wait_for_timeout(1000)

    bag_weight_id = api_context.get(
        f"/api/inventory-process/supply-request/{bag_ready_to_weigh['request_id']}/bagweight-id"
    ).json()
    assert bag_weight_id, "Expected a bagweight record to exist after submitting the weighing form"
