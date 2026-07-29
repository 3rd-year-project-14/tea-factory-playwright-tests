from playwright.sync_api import Page, expect


class LoginPage:
    """POM wrapper for Auth.jsx. Reused by every test that needs an authenticated
    session -- kept here instead of duplicating the fill/click sequence in each
    test file (previously copy-pasted as a local `login()` helper in ~10 files)."""

    URL_PATH = "/login"

    def __init__(self, page: Page, frontend_url: str):
        self.page = page
        self.frontend_url = frontend_url

    def goto(self):
        self.page.goto(f"{self.frontend_url}{self.URL_PATH}")
        return self

    def login(self, email: str, password: str):
        self.page.get_by_placeholder("Enter your email").fill(email)
        self.page.get_by_placeholder("Enter your password").fill(password)
        self.page.get_by_role("button", name="Sign In").click()
        return self

    def expect_login_succeeded(self):
        expect(self.page).not_to_have_url(f"{self.frontend_url}{self.URL_PATH}", timeout=10000)
        expect(self.page.get_by_text("Invalid credentials")).not_to_be_visible()

    def expect_login_failed(self):
        expect(self.page.get_by_text("Invalid credentials")).to_be_visible(timeout=10000)
        expect(self.page).to_have_url(f"{self.frontend_url}{self.URL_PATH}")
