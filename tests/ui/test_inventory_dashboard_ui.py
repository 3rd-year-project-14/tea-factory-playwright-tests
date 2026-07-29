import os

import pytest
from playwright.sync_api import Page, expect

from conftest import FRONTEND_URL

# Read-only smoke test: InventoryRoutesPage.jsx falls back to dummy data
# (inventoryData.jsx) if the live API call fails, so this only asserts the dashboard
# chrome renders correctly, not any specific numbers -- those depend on whatever
# inventory data actually exists for factory 1 at test time.


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


def login(page: Page):
    page.goto(f"{FRONTEND_URL}/login")
    page.get_by_placeholder("Enter your email").fill(os.environ["TEST_USER_EMAIL"])
    page.get_by_placeholder("Enter your password").fill(os.environ["TEST_USER_PASSWORD"])
    page.get_by_role("button", name="Sign In").click()
    expect(page).not_to_have_url(f"{FRONTEND_URL}/login", timeout=10000)


def test_inventory_dashboard_shows_summary_cards(page: Page, as_factory_manager):
    login(page)
    page.goto(f"{FRONTEND_URL}/factoryManager/inventory")

    expect(page.get_by_text("Inventory Management")).to_be_visible(timeout=10000)
    expect(page.get_by_text("Total Weight", exact=True)).to_be_visible()
    expect(page.get_by_text("Total Bags", exact=True)).to_be_visible()
    expect(page.get_by_text("Net Weight", exact=True)).to_be_visible()


def test_inventory_dashboard_daily_monthly_toggle(page: Page, as_factory_manager):
    login(page)
    page.goto(f"{FRONTEND_URL}/factoryManager/inventory")

    monthly_button = page.get_by_role("button", name="Monthly")
    expect(monthly_button).to_be_visible(timeout=10000)
    monthly_button.click()

    expect(page.get_by_text("Month:")).to_be_visible()
    expect(page.get_by_text("Year:")).to_be_visible()
