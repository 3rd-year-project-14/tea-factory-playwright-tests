import os
import uuid

import pytest
from playwright.sync_api import Page, expect

from conftest import FRONTEND_URL

# Real, backend-wired flow: addManagers.jsx creates a Firebase account
# (createUserWithEmailAndPassword) then POSTs to /api/users. Same environment
# tolerance as tests/ui/test_driver_vehicle_ui.py's driver-creation test: the Firebase
# account itself has no cleanup here (no Admin SDK access from these Python tests),
# only the resulting backend DB row is cleaned up.
#
# GAP FOUND (not fixed -- out of scope for this test to implement): addManagers.jsx
# sends `factoryId: formData.factory` as a flat field in the POST /api/users body, but
# UserDTO (backend) has no `factoryId` field -- only a nested `factory: FactoryDTO`.
# Jackson silently drops unknown JSON properties (no FAIL_ON_UNKNOWN_PROPERTIES), so
# `userDTO.getFactory()` is always null and UserService.applyFactory() never runs.
# The manager's role is saved correctly but their factory assignment is silently
# dropped every time, regardless of which factory was picked in the UI. Confirmed by
# selecting a factory, reading the (correctly populated) input value right before
# submit, and then finding factory_id NULL in the DB afterward.


@pytest.fixture
def as_owner(db_conn):
    """OwnerRoutes is only mounted in AppRouter when user.role === 'OWNER'."""
    cur = db_conn.cursor()
    cur.execute(
        "UPDATE users SET role = 'OWNER', factory_id = NULL WHERE email = %s",
        (os.environ["TEST_USER_EMAIL"],),
    )
    cur.close()

    yield

    cur = db_conn.cursor()
    cur.execute(
        "UPDATE users SET role = 'PENDING_USER' WHERE email = %s",
        (os.environ["TEST_USER_EMAIL"],),
    )
    cur.close()


@pytest.fixture
def new_manager_email(db_conn):
    unique = uuid.uuid4().hex[:8]
    email = f"pw-manager-ui-{unique}@test.com"

    yield email, unique

    cur = db_conn.cursor()
    cur.execute("DELETE FROM users WHERE email = %s", (email,))
    cur.close()


def login(page: Page):
    page.goto(f"{FRONTEND_URL}/login")
    page.get_by_placeholder("Enter your email").fill(os.environ["TEST_USER_EMAIL"])
    page.get_by_placeholder("Enter your password").fill(os.environ["TEST_USER_PASSWORD"])
    page.get_by_role("button", name="Sign In").click()
    expect(page).not_to_have_url(f"{FRONTEND_URL}/login", timeout=10000)


def test_creating_manager_via_ui_creates_role_but_drops_factory_assignment(
    page: Page, db_conn, as_owner, new_manager_email
):
    email, unique = new_manager_email

    login(page)
    page.goto(f"{FRONTEND_URL}/Owner/ManagerView/addManagers")

    page.get_by_placeholder("Enter manager name").fill("PW UI Manager")
    page.get_by_placeholder("Enter manager address").fill("Test Address, Kandy")
    page.get_by_placeholder("Enter NIC number").fill(f"PWM{unique}")
    page.get_by_placeholder("Enter mobile number").fill("0771234567")
    page.get_by_placeholder("Enter email address").fill(email)
    page.get_by_placeholder("Enter password").fill("Password123!")

    page.get_by_placeholder("Select Role").click()
    page.get_by_role("button", name="Factory Manager").click()

    page.get_by_placeholder("Select Factory").click()
    page.get_by_role("button", name="Wawlugala Tea Factory").click()

    page.get_by_role("button", name="Save & Give Access").click()
    page.wait_for_timeout(1500)

    cur = db_conn.cursor()
    cur.execute("SELECT role, factory_id FROM users WHERE email = %s", (email,))
    row = cur.fetchone()
    cur.close()

    assert row is not None, "Expected a backend user to be created for the new manager"
    role, factory_id = row
    assert role == "FACTORY_MANAGER"
    assert factory_id is None, (
        "Manager's factory_id was persisted -- if addManagers.jsx's payload was fixed "
        "to send a nested `factory` object (matching UserDTO), update this test to "
        "assert factory_id == 1 instead."
    )
