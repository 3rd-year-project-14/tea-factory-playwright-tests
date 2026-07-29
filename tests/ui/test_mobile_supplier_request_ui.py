import os

import pytest
from playwright.sync_api import Page, expect

from conftest import MOBILE_FRONTEND_URL

# This drives the supplier-side registration flow from tea-factory-mobile-app (Expo),
# not the web app -- FactoryManager's web UI only reviews/approves requests that
# already exist (see tests/ui/test_supplier_registration_ui.py's NOTE). The mobile app
# has no test framework of its own (no Detox/Appium, no jest config), so this reuses
# the existing Playwright setup against the app's `expo start --web` build instead of
# standing up a whole new native E2E toolchain.
#
# Getting the web build to bundle at all required two small source fixes, made
# alongside these tests (not gap documentation -- these were straightforward bugs):
#   1. metro.config.js (new) aliases react-native-maps to mocks/react-native-maps.web.js
#      on web only. react-native-maps has no web target; because expo-router eagerly
#      bundles every route, one native-only import anywhere broke the *entire* web
#      bundle, not just the map's own screen.
#   2. app/index.jsx used `useEffect(() => router.replace('/login'), [])`, which can
#      fire before expo-router's navigator finishes mounting -- most visible on web --
#      throwing "Attempted to navigate before mounting the Root Layout component" on
#      every load. Replaced with a declarative <Redirect href="/login" />.
#
# GAP FOUND (not fixed -- out of scope for this test to implement): in
# app/(role)/(pending)/index.jsx, handleSubmitSupplierRequest() catches its own
# errors internally (shows an error Toast, then returns normally instead of
# rethrowing). The "Finish" button's onPress does
#   await handleSubmitSupplierRequest();
#   Toast.show({ type: "success", text1: "Application Submitted! ..." });
# with no try/catch of its own, so that unconditional success toast (and the
# subsequent redirect to /(nontabs)) fires *even when the submission failed* --
# e.g. because no NIC image was attached, which the backend requires
# (@RequestPart(value = "nicImage") with no `required = false`). A supplier sees
# "Application Submitted! You will be approved soon." while no supplier_request row
# was ever created. This test proves that gap (finishing without a NIC image shows
# success but creates nothing) so it starts failing -- flagging for review -- if
# someone fixes the error handling later.


@pytest.fixture
def as_pending_user(db_conn):
    """The shared TEST_USER must be a fresh PENDING_USER with no existing supplier
    request for this flow to be reachable (SupplierRequestService rejects a second
    request per user)."""
    cur = db_conn.cursor()
    cur.execute(
        "UPDATE users SET role = 'PENDING_USER', factory_id = NULL WHERE email = %s",
        (os.environ["TEST_USER_EMAIL"],),
    )
    cur.execute("SELECT id FROM users WHERE email = %s", (os.environ["TEST_USER_EMAIL"],))
    user_id = cur.fetchone()[0]
    cur.execute("DELETE FROM supplier_request WHERE user_id = %s", (user_id,))
    cur.close()

    yield user_id

    cur = db_conn.cursor()
    cur.execute("DELETE FROM supplier WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM supplier_request WHERE user_id = %s", (user_id,))
    cur.close()


def login(page: Page):
    page.goto(f"{MOBILE_FRONTEND_URL}/login")
    page.get_by_placeholder("Enter email").fill(os.environ["TEST_USER_EMAIL"])
    page.get_by_placeholder("Enter password").fill(os.environ["TEST_USER_PASSWORD"])
    page.get_by_text("Login", exact=True).last.click()
    try:
        expect(page.get_by_text("Complete your account to start supplying")).to_be_visible(timeout=8000)
    except AssertionError:
        # Occasional cold-start race in the Expo web build (same class of flake as
        # test_payment_processing_ui.py's adhoc-queue fetch) -- retry once.
        page.get_by_placeholder("Enter email").fill(os.environ["TEST_USER_EMAIL"])
        page.get_by_placeholder("Enter password").fill(os.environ["TEST_USER_PASSWORD"])
        page.get_by_text("Login", exact=True).last.click()
        expect(page.get_by_text("Complete your account to start supplying")).to_be_visible(timeout=10000)


def fill_map_field(page: Page, placeholder: str):
    page.get_by_placeholder(placeholder).click(force=True)
    expect(page.get_by_test_id("map-view-mock")).to_be_visible(timeout=10000)
    page.get_by_test_id("map-view-mock").click(position={"x": 300, "y": 200})
    page.get_by_text("Confirm Location", exact=True).click()


def complete_steps_1_and_2(page: Page):
    page.get_by_text("Select factory").click()
    page.get_by_test_id("Miyanawathura Tea Factory").click()
    page.get_by_text("Next", exact=True).click()

    expect(page.get_by_text("Land Details")).to_be_visible(timeout=10000)
    page.get_by_placeholder("Enter Land Size (acres)").fill("2.5")
    fill_map_field(page, "Tap to select Land Location")
    fill_map_field(page, "Tap to select Pickup Location")
    page.get_by_placeholder("Enter Monthly Supply (kg)").fill("100")
    page.get_by_text("Next", exact=True).click()

    expect(page.get_by_text("NIC Verification")).to_be_visible(timeout=10000)


def test_wizard_reaches_nic_step_with_entered_data_intact(page: Page, as_pending_user):
    login(page)
    complete_steps_1_and_2(page)

    expect(page.get_by_text("Tap to upload NIC")).to_be_visible()


def test_finishing_without_nic_image_falsely_reports_success(
    page: Page, api_context, as_pending_user
):
    login(page)
    complete_steps_1_and_2(page)

    page.get_by_text("Finish", exact=True).click()

    expect(page.get_by_text("Application Submitted!", exact=False)).to_be_visible(timeout=10000)

    requests = api_context.get(f"/api/supplier-requests?userId={as_pending_user}").json()
    assert requests == [], (
        "A supplier_request was actually created without a NIC image -- if the backend "
        "or the mobile app's error handling changed, update this test to assert the "
        "success message reflects a real created request instead."
    )
