import os

import pytest
from playwright.sync_api import Page, expect

from conftest import FRONTEND_URL

# AppRouter.jsx has no ProtectedRoute/redirect-on-wrong-role wrapper -- role-based
# access is just conditional route mounting:
#   {user?.role === "FACTORY_MANAGER" && FactoryManagerRoutes}
# So visiting another role's path with a mismatched role matches no <Route> at all --
# there's no "Forbidden" page and no redirect, the router just renders nothing inside
# the layout. This test documents that behavior (not a redirect) so it starts failing
# -- flagging for review -- if a real role guard is added later.


@pytest.fixture
def as_inventory_manager(db_conn):
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


def login(page: Page):
    page.goto(f"{FRONTEND_URL}/login")
    page.get_by_placeholder("Enter your email").fill(os.environ["TEST_USER_EMAIL"])
    page.get_by_placeholder("Enter your password").fill(os.environ["TEST_USER_PASSWORD"])
    page.get_by_role("button", name="Sign In").click()
    expect(page).not_to_have_url(f"{FRONTEND_URL}/login", timeout=10000)


def test_own_role_route_is_reachable(page: Page, as_inventory_manager):
    login(page)
    page.goto(f"{FRONTEND_URL}/inventoryManager/leaf_weight")

    expect(page).to_have_url(f"{FRONTEND_URL}/inventoryManager/leaf_weight")
    # Sanity check the mounted route actually rendered something, not a blank shell.
    expect(page.locator("body")).not_to_be_empty()


def test_mismatched_role_route_renders_no_content_instead_of_redirecting(
    page: Page, as_inventory_manager
):
    login(page)
    page.goto(f"{FRONTEND_URL}/factoryManager/suppliers")

    # No route matches (FactoryManagerRoutes isn't mounted for INVENTORY_MANAGER), and
    # there's no catch-all redirect either, so the URL stays put and FactoryManager
    # content never appears -- unlike a real guard, which would redirect elsewhere.
    expect(page).to_have_url(f"{FRONTEND_URL}/factoryManager/suppliers")
    expect(page.get_by_text("Supplier Management")).not_to_be_visible()
