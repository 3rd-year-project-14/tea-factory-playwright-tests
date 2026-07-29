import os

import pytest
from playwright.sync_api import Page

from conftest import FRONTEND_URL
from pages.login_page import LoginPage
from utils.test_data import load_test_data

pytestmark = pytest.mark.ui


@pytest.mark.smoke
def test_valid_login_redirects_away_from_login_page(page: Page):
    login_page = LoginPage(page, FRONTEND_URL).goto()
    login_page.login(os.environ["TEST_USER_EMAIL"], os.environ["TEST_USER_PASSWORD"])

    login_page.expect_login_succeeded()


@pytest.mark.smoke
def test_invalid_login_shows_error(page: Page):
    invalid = load_test_data()["invalid_login"]

    login_page = LoginPage(page, FRONTEND_URL).goto()
    login_page.login(invalid["email"], invalid["password"])

    login_page.expect_login_failed()
