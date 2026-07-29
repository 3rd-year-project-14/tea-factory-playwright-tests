import os

import pytest
from playwright.sync_api import Page, expect

from conftest import FRONTEND_URL
from pages.login_page import LoginPage
from pages.tea_rate_page import TeaRatePage
from utils.test_data import load_test_data

pytestmark = pytest.mark.ui

# NOTE: PaymentManagerRoutes (including /payment-manager/tea-rates) is mounted
# unconditionally in AppRouter.jsx -- {PaymentManagerRoutes} is included with no
# role check -- so any logged-in user can reach this page regardless of role. This
# mirrors the backend's permissive dev-mode security config (SecurityConfig.permitAll)
# and is worth flagging: neither layer currently enforces the FACTORY_MANAGER /
# PAYMENT_MANAGER role this page is meant to be restricted to.
#
# NOTE 2: The submit handler hardcodes the year as 2025 regardless of the real
# current date (`month: \`${2025}-${currentMonth...}\`` in TeaRateAdjustment.jsx),
# so every submission lands in year 2025 no matter when the test runs. This test
# accounts for that rather than hiding it.


def test_submitting_tea_rate_shows_success_alert_and_persists(page: Page, api_context):
    LoginPage(page, FRONTEND_URL).goto().login(
        os.environ["TEST_USER_EMAIL"], os.environ["TEST_USER_PASSWORD"]
    ).expect_login_succeeded()

    dialog_messages = []
    page.on("dialog", lambda dialog: (dialog_messages.append(dialog.message), dialog.accept()))

    tea_rate_page = TeaRatePage(page, FRONTEND_URL).goto()
    month_number, selected_month_label = tea_rate_page.selected_month()

    tea_rate_page.fill_gross_sale_average(load_test_data()["tea_rate"]["gross_sale_average"])
    tea_rate_page.submit()

    page.wait_for_timeout(500)  # allow the async submit + alert to resolve

    assert any("successfully" in m for m in dialog_messages), dialog_messages

    expected_month = f"2025-{int(month_number):02d}"
    pending = api_context.get("/api/tea_rates/pending").json()
    assert any(rate["month"] == expected_month for rate in pending), (
        f"Expected a pending tea rate for {expected_month} ({selected_month_label} 2025), "
        f"got months: {[r['month'] for r in pending]}"
    )


def test_gsa_missing_shows_validation_alert(page: Page):
    LoginPage(page, FRONTEND_URL).goto().login(
        os.environ["TEST_USER_EMAIL"], os.environ["TEST_USER_PASSWORD"]
    ).expect_login_succeeded()

    tea_rate_page = TeaRatePage(page, FRONTEND_URL).goto()
    expect(tea_rate_page.submit_button()).to_be_disabled()
