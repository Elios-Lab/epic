"""UI tests for the landing page and authentication flow."""

import pytest
from playwright.sync_api import Page, expect


def _go_to_login(page: Page):
    """Click the landing page 'Log in' button to open the login form."""
    page.get_by_role("button", name="Log in").click()
    page.wait_for_selector("input[type='password']", timeout=3000)


def test_landing_page_loads(unauth_page: Page):
    """Landing page should display the EPIC title and a Log In button."""
    expect(unauth_page.get_by_text("EPIC", exact=False).first).to_be_visible()
    expect(unauth_page.get_by_role("button", name="Log in")).to_be_visible()


def test_login_form_appears(unauth_page: Page):
    """Clicking Log In should show the login form with username and password fields."""
    _go_to_login(unauth_page)
    expect(unauth_page.get_by_label("Username")).to_be_visible()
    expect(unauth_page.get_by_label("Password")).to_be_visible()
    # Submit button inside the form.
    expect(unauth_page.locator("form").get_by_role("button", name="Log in")).to_be_visible()


def test_invalid_login_shows_error(unauth_page: Page):
    """Submitting wrong credentials should show an error message."""
    _go_to_login(unauth_page)
    unauth_page.get_by_label("Username").fill("nobody")
    unauth_page.get_by_label("Password").fill("wrongpass")
    unauth_page.locator("form").get_by_role("button", name="Log in").click()
    expect(unauth_page.locator("[class*='red']").first).to_be_visible(timeout=3000)


def test_admin_login_reaches_dashboard(unauth_page: Page):
    """Admin credentials should land on the Administrator Dashboard."""
    _go_to_login(unauth_page)
    unauth_page.get_by_label("Username").fill("admin")
    unauth_page.get_by_label("Password").fill("admin-password")
    unauth_page.locator("form").get_by_role("button", name="Log in").click()
    expect(unauth_page.get_by_text("Administrator Dashboard")).to_be_visible(timeout=5000)


def test_logout_returns_to_landing(unauth_page: Page):
    """Clicking Logout should return to the landing page."""
    _go_to_login(unauth_page)
    unauth_page.get_by_label("Username").fill("admin")
    unauth_page.get_by_label("Password").fill("admin-password")
    unauth_page.locator("form").get_by_role("button", name="Log in").click()
    unauth_page.wait_for_selector("text=Administrator Dashboard", timeout=5000)
    unauth_page.get_by_role("button", name="Logout").click()
    expect(unauth_page.get_by_role("button", name="Log in")).to_be_visible(timeout=3000)
