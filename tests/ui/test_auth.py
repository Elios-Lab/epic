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


def _create_invitation(live_server: str, organizer_token: str, email: str) -> str:
    """Create a contest + invitation via the API; read the token from the UI test DB."""
    import sqlite3

    import requests

    from tests.ui.conftest import create_active_contest

    contest = create_active_contest(live_server, organizer_token)
    response = requests.post(
        f"{live_server}/api/v1/contests/{contest['contest_id']}/invitations",
        json={"emails": [email]},
        headers={"Authorization": f"Bearer {organizer_token}"},
    )
    assert response.status_code == 201

    # Tokens are intentionally never exposed by the API — read it from the DB.
    conn = sqlite3.connect("./test_ui.db")
    try:
        row = conn.execute(
            "SELECT token FROM invitations WHERE email = ? ORDER BY created_at DESC",
            (email,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return row[0]


def test_invitation_link_shows_registration_form(
    unauth_page: Page, live_server: str, organizer_token: str
):
    """Following an invitation deep link must show the registration form with
    the contest name, not a 404."""
    token = _create_invitation(live_server, organizer_token, "invitee1@example.com")

    unauth_page.goto(f"{live_server}/register?token={token}")
    expect(unauth_page.get_by_role("heading", name="Join EPIC")).to_be_visible()
    expect(unauth_page.get_by_text("invitee1@example.com")).to_be_visible()
    expect(unauth_page.get_by_role("button", name="Create account")).to_be_visible()


def test_invitation_registration_completes_and_logs_in(
    unauth_page: Page, live_server: str, organizer_token: str
):
    """Completing the registration form must create the account and land the
    new participant on their dashboard, already logged in."""
    token = _create_invitation(live_server, organizer_token, "invitee2@example.com")

    unauth_page.goto(f"{live_server}/register?token={token}")
    unauth_page.get_by_label("First name").fill("Ada")
    unauth_page.get_by_label("Last name").fill("Lovelace")
    unauth_page.get_by_label("Password", exact=True).fill("super-secret-99")
    unauth_page.get_by_label("Confirm password").fill("super-secret-99")
    unauth_page.get_by_role("button", name="Create account").click()

    expect(
        unauth_page.get_by_role("heading", name="Participant Dashboard")
    ).to_be_visible(timeout=5000)
    expect(unauth_page.get_by_text("invitee2@example.com").first).to_be_visible()


def test_invalid_invitation_token_shows_error(unauth_page: Page, live_server: str):
    """A bad token must show a clear error instead of a registration form."""
    unauth_page.goto(f"{live_server}/register?token=not-a-real-token")
    expect(
        unauth_page.get_by_text("invalid, expired, or already used")
    ).to_be_visible(timeout=5000)
