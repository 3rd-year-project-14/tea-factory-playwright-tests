from playwright.sync_api import Page, expect


class TeaRatePage:
    """POM wrapper for TeaRateAdjustment.jsx (payment-manager/tea-rates) -- the
    one real, backend-wired form in the Payment Manager area. See
    UI_TESTS_INTERVIEW_GUIDE.md for why the other "management" pages don't get
    a page object (mock/read-only, nothing stable to wrap)."""

    URL_PATH = "/payment-manager/tea-rates"

    def __init__(self, page: Page, frontend_url: str):
        self.page = page
        self.frontend_url = frontend_url

    def goto(self):
        self.page.goto(f"{self.frontend_url}{self.URL_PATH}")
        return self

    def selected_month(self) -> tuple[str, str]:
        """Returns (month_number, month_label) for whatever month is preselected."""
        month_select = self.page.get_by_role("combobox")
        return month_select.input_value(), month_select.locator("option:checked").inner_text()

    def fill_gross_sale_average(self, value: str):
        self.page.get_by_placeholder("Gross Sale Average").fill(value)
        return self

    def submit_button(self):
        return self.page.get_by_role("button", name="Submit for Approval")

    def submit(self):
        button = self.submit_button()
        expect(button).to_be_enabled()
        button.click()
        return self
