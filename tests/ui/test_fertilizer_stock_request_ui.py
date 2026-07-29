import os
import uuid

import pytest
from playwright.sync_api import Page, expect

from conftest import FRONTEND_URL
from pages.fertilizer_stock_request_page import FertilizerStockRequestPage
from pages.login_page import LoginPage
from utils.test_data import load_test_data


pytestmark = pytest.mark.ui

# This is the real, backend-wired form (unlike CreateRoute.jsx or the fertilizer
# approve/reject pages, which turned out to be mock/dead-code). It submits via
# POST /api/fertilizer-requests/fertilizer-stock-requests -- a *different* backend
# flow from the supplier-facing /api/supplier-fertilizer-requests already covered in
# tests/api/test_fertilizer.py: this one is a factory-side "request more stock from a
# company" flow, not a supplier requesting fertilizer for their own farm.


@pytest.fixture
def as_fertilizer_manager(db_conn):
    """FertilizerManagerRoutes is only mounted in AppRouter when user.role ===
    'FERTILIZER_MANAGER'."""
    cur = db_conn.cursor()
    cur.execute(
        "UPDATE users SET role = 'FERTILIZER_MANAGER', factory_id = 1 WHERE email = %s",
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
def fertilizer_company_and_category(api_context):
    """No cleanup -- same reasoning as tests/api/test_fertilizer.py: the company
    DELETE endpoint fails on the company_category link table, and categories have
    no delete endpoint at all. Leftover rows are harmless."""
    unique = uuid.uuid4().hex[:8]
    response = api_context.post(
        "/api/fertilizer-companies",
        data={
            "name": f"PW UI Fert Co {unique}",
            "address": "Kandy",
            "contactPerson": "Test",
            "contactNumber": "0771234567",
            "email": f"pwuifert-{unique}@test.com",
            "categories": [f"PW UI Category {unique}"],
        },
    )
    assert response.status == 200
    body = response.json()
    return {"category_name": f"PW UI Category {unique}", "company_name": f"PW UI Fert Co {unique}"}


def test_submitting_stock_request_creates_it_via_api(
    page: Page, api_context, as_fertilizer_manager, fertilizer_company_and_category
):
    LoginPage(page, FRONTEND_URL).goto().login(
        os.environ["TEST_USER_EMAIL"], os.environ["TEST_USER_PASSWORD"]
    ).expect_login_succeeded()

    request_data = load_test_data()["fertilizer_stock_request"]

    stock_request_page = FertilizerStockRequestPage(page, FRONTEND_URL).goto()
    stock_request_page.select_fertilizer_type(fertilizer_company_and_category["category_name"])
    stock_request_page.select_company(fertilizer_company_and_category["company_name"])
    stock_request_page.fill_quantity(request_data["quantity"])
    stock_request_page.fill_notes(request_data["notes"])
    stock_request_page.submit()

    # Form resets and the new request is prepended to the visible list on success.
    stock_request_page.expect_request_visible(fertilizer_company_and_category["company_name"])
    expect(stock_request_page.quantity_input()).to_have_value("")

    # Cross-verify against the backend rather than trusting the UI alone.
    requests = api_context.get("/api/fertilizer-requests/fertilizer-stock-requests").json()
    matching = [
        r for r in requests if r.get("companyName") == fertilizer_company_and_category["company_name"]
    ]
    assert matching, "Submitted stock request was not found via the API"
    assert matching[0]["quantity"] == int(request_data["quantity"])
    assert matching[0]["note"] == request_data["notes"]


def test_company_dropdown_disabled_until_fertilizer_type_selected(page: Page, as_fertilizer_manager):
    LoginPage(page, FRONTEND_URL).goto().login(
        os.environ["TEST_USER_EMAIL"], os.environ["TEST_USER_PASSWORD"]
    ).expect_login_succeeded()

    stock_request_page = FertilizerStockRequestPage(page, FRONTEND_URL).goto()
    expect(stock_request_page.company_dropdown()).to_be_disabled()
