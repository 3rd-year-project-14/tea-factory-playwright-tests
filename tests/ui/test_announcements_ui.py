import os
import uuid

import pytest
from playwright.sync_api import Page, expect

from conftest import FRONTEND_URL

# Real, backend-wired form: addAnnouncement.jsx POSTs multipart/form-data to
# /api/announcements (field names topic/subject/content/factories/attachments match
# tests/api/test_announcements.py exactly). No success alert/toast exists -- on
# success it just navigate(-1)s back to the list page, so this test cross-checks the
# result via the API rather than any UI success message.
#
# No file is attached here: the backend's file upload also goes through Firebase
# Storage, whose billing account is disabled in this environment -- the same
# limitation documented in tests/api/test_supplier_request.py for NIC images (confirmed
# here too: attaching a file makes POST /api/announcements 500 with "Failed to upload
# file"). Attachments are optional (tests/api/test_announcements.py's
# test_create_announcement omits them entirely), so this test does too.


@pytest.fixture
def as_owner(db_conn):
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


def login(page: Page):
    page.goto(f"{FRONTEND_URL}/login")
    page.get_by_placeholder("Enter your email").fill(os.environ["TEST_USER_EMAIL"])
    page.get_by_placeholder("Enter your password").fill(os.environ["TEST_USER_PASSWORD"])
    page.get_by_role("button", name="Sign In").click()
    expect(page).not_to_have_url(f"{FRONTEND_URL}/login", timeout=10000)


def test_creating_announcement_via_ui_persists_via_api(page: Page, api_context, as_owner):
    subject = f"PW UI Announcement {uuid.uuid4().hex[:8]}"

    login(page)
    page.goto(f"{FRONTEND_URL}/owner/annoucement")

    page.get_by_role("button", name="Add New").click()
    expect(page).to_have_url(f"{FRONTEND_URL}/owner/annoucement/add", timeout=10000)

    page.locator("select").select_option(index=1)
    page.get_by_placeholder("Enter announcement subject").fill(subject)
    page.get_by_placeholder("Enter announcement content").fill("Playwright UI test content")

    page.get_by_text("Select factories").click()
    # The factory checkboxes are `readOnly` (checked state driven by React, not native
    # toggling), so Playwright's .check() -- which clicks then verifies the native
    # `checked` property flipped -- never settles. A plain .click() (which just
    # triggers the onClick handler React actually listens to) works.
    page.get_by_role("checkbox").first.click()

    page.get_by_role("button", name="Save Announcement").click()

    expect(page).to_have_url(f"{FRONTEND_URL}/owner/annoucement", timeout=10000)

    announcements = api_context.get("/api/announcements").json()
    matching = [a for a in announcements if a.get("subject") == subject]
    assert matching, "Submitted announcement was not found via the API"
    assert matching[0]["content"] == "Playwright UI test content"
