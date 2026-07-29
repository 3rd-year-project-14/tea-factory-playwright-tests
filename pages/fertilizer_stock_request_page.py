from playwright.sync_api import Page, expect


class FertilizerStockRequestPage:
    """POM wrapper for stockRequest.jsx (fertilizerManager/stocks/request) -- the
    factory-side "request more stock from a company" form. Backed by
    POST /api/fertilizer-requests/fertilizer-stock-requests."""

    URL_PATH = "/fertilizerManager/stocks/request"

    def __init__(self, page: Page, frontend_url: str):
        self.page = page
        self.frontend_url = frontend_url

    def goto(self):
        self.page.goto(f"{self.frontend_url}{self.URL_PATH}")
        return self

    def select_fertilizer_type(self, category_name: str):
        self.page.locator('select[name="fertilizerType"]').select_option(label=category_name)
        return self

    def select_company(self, company_name: str):
        self.page.locator('select[name="company"]').select_option(label=company_name)
        return self

    def company_dropdown(self):
        return self.page.locator('select[name="company"]')

    def quantity_input(self):
        return self.page.locator('input[name="quantity"]')

    def fill_quantity(self, value: str):
        self.quantity_input().fill(value)
        return self

    def fill_notes(self, value: str):
        self.page.locator('textarea[name="notes"]').fill(value)
        return self

    def submit_button(self):
        return self.page.get_by_role("button", name="Submit Request")

    def submit(self):
        self.submit_button().click()
        return self

    def expect_request_visible(self, company_name: str):
        expect(self.page.locator("p", has_text=company_name)).to_be_visible(timeout=10000)
