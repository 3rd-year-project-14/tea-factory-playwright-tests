import os
import uuid

import pytest
from playwright.sync_api import Page, expect

from conftest import FRONTEND_URL

# GAP FOUND (not fixed -- out of scope for this test to implement): AddVehicle.jsx's
# handleSubmit is not wired to the backend at all -- it just alert()s a JSON dump of
# the form and never calls the vehicles API (POST /api/vehicles, covered in
# tests/api/test_vehicles.py). Its field names also don't match that API's shape
# (vehicleNumber/vehicleType/free-text capacity vs. vehicleNo/model/numeric capacity).
# This test proves the form is a no-op against the backend, same style as
# test_route_creation_ui.py's CreateRoute gap test.


@pytest.fixture
def as_transport_manager(db_conn):
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


def test_register_vehicle_form_is_not_wired_to_backend(page: Page, api_context, as_transport_manager):
    vehicle_no = f"PW-UI-{uuid.uuid4().hex[:6].upper()}"

    before = api_context.get("/api/vehicles").json()

    login(page)
    page.goto(f"{FRONTEND_URL}/transportManager/vehicle/add")

    page.locator('input[name="vehicleNumber"]').fill(vehicle_no)
    page.locator('select[name="vehicleType"]').select_option(index=1)
    page.locator('input[name="capacity"]').fill("1000kg")
    # lastServiceDate is `required` -- leaving it empty blocks HTML5 form submission
    # entirely (no submit handler fires, no alert, nothing to assert on).
    page.locator('input[name="lastServiceDate"]').fill("2026-01-01")

    dialog_messages = []
    page.on("dialog", lambda dialog: (dialog_messages.append(dialog.message), dialog.accept()))
    page.get_by_role("button", name="Register Vehicle").click()
    page.wait_for_timeout(500)

    assert any("registered successfully" in m for m in dialog_messages), dialog_messages

    after = api_context.get("/api/vehicles").json()
    assert len(after) == len(before), (
        "Vehicle count changed after submitting the Register Vehicle form -- if this "
        "form was just wired to the backend, update this test to assert the vehicle "
        "was created via POST /api/vehicles and remove this gap-tracking assertion."
    )
    assert not any(v.get("vehicleNo") == vehicle_no for v in after)


@pytest.fixture
def new_driver_email(db_conn):
    """Real Firebase account creation (createUserWithEmailAndPassword) has no
    cleanup here -- same tolerance as the pending_user/firebase_id_token fixtures
    elsewhere in this suite (no Firebase Admin SDK access from these Python tests).
    Only the resulting backend DB row is cleaned up."""
    unique = uuid.uuid4().hex[:8]
    email = f"pw-driver-ui-{unique}@test.com"

    yield email, unique

    cur = db_conn.cursor()
    cur.execute("DELETE FROM users WHERE email = %s", (email,))
    cur.close()


def test_add_driver_user_creates_backend_user(page: Page, db_conn, as_transport_manager, new_driver_email):
    email, unique = new_driver_email

    login(page)
    page.goto(f"{FRONTEND_URL}/transportManager/drivers/user")

    page.get_by_placeholder("e.g. Kasun Perera").fill("PW UI Driver")
    page.get_by_placeholder("e.g. example@email.com").fill(email)
    page.get_by_placeholder("e.g. 881234567V").fill(f"PWD{unique}")
    page.get_by_placeholder("e.g. 0771234567").fill("0771234567")
    page.get_by_placeholder("At least 8 characters").fill("Password123!")
    page.get_by_placeholder("e.g. B1234567").fill(f"LIC{unique}")
    page.get_by_placeholder("e.g. WP CD-1234").fill(f"WP CD-{unique[:4]}")
    page.get_by_placeholder("Driver address").fill("Test Address, Kandy")

    page.get_by_role("button", name="Create Driver Account").click()
    # Creation round-trips through real Firebase (signInWithPassword, lookup, signUp,
    # lookup again) before the backend POST -- a fixed short wait is flaky under load,
    # so wait for the page to actually navigate away instead (handleSubmit's
    # navigate(-1) only fires after the backend call resolves).
    expect(page).not_to_have_url(f"{FRONTEND_URL}/transportManager/drivers/user", timeout=15000)

    cur = db_conn.cursor()
    cur.execute("SELECT role FROM users WHERE email = %s", (email,))
    row = cur.fetchone()
    cur.close()

    assert row is not None, "Expected a backend user to be created for the new driver"
    assert row[0] in ("DRIVER", "PENDING_USER")
