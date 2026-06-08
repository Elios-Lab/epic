"""UI tests for the Administrator dashboard."""

import uuid

import pytest
from playwright.sync_api import Page, expect

from tests.ui.conftest import close_contest, create_active_contest


@pytest.fixture
def admin_page(browser_context, live_server):
    """Open a fresh page logged in as admin."""
    import requests
    resp = requests.post(
        f"{live_server}/api/v1/auth/login",
        json={"username": "admin", "password": "admin-password"},
    )
    token = resp.json()["access_token"]
    pg = browser_context.new_page()
    pg.goto(live_server)
    pg.evaluate(f"() => localStorage.setItem('epic_token', '{token}')")
    pg.reload()
    pg.wait_for_load_state("networkidle")
    yield pg
    pg.close()


# ── Dashboard overview ────────────────────────────────────────────────────────

def test_admin_dashboard_loads(admin_page: Page):
    """Admin should see the Administrator Dashboard."""
    expect(admin_page.get_by_text("Administrator Dashboard")).to_be_visible(timeout=5000)


def test_admin_overview_shows_stats(admin_page: Page):
    """The Overview tab should show platform statistics cards."""
    expect(admin_page.get_by_text("Total contests")).to_be_visible(timeout=5000)
    expect(admin_page.get_by_text("Registered users")).to_be_visible(timeout=5000)


# ── Contests table ────────────────────────────────────────────────────────────

def test_admin_contests_tab_shows_table(admin_page: Page):
    """The Contests tab in the overview should show a table with Name and Status columns."""
    # The admin view shows the contests table directly on the overview tab.
    expect(admin_page.get_by_role("columnheader", name="Name")).to_be_visible(timeout=5000)
    expect(admin_page.get_by_role("columnheader", name="Status")).to_be_visible(timeout=5000)


def test_admin_can_see_active_contest_in_table(
    admin_page: Page, live_server: str, organizer_token: str
):
    """An ACTIVE contest created by an organizer should appear in the admin table."""
    contest = create_active_contest(live_server, organizer_token)
    try:
        admin_page.reload()
        admin_page.wait_for_load_state("networkidle")
        expect(admin_page.get_by_role("cell", name=contest["name"])).to_be_visible(timeout=5000)
    finally:
        close_contest(live_server, organizer_token, contest["contest_id"])


def test_admin_monitor_button_visible_for_active_contest(
    admin_page: Page, live_server: str, organizer_token: str
):
    """The Monitor button should appear in the admin table for ACTIVE contests."""
    contest = create_active_contest(live_server, organizer_token)
    try:
        admin_page.reload()
        admin_page.wait_for_load_state("networkidle")
        row = admin_page.locator("tr").filter(has_text=contest["name"])
        expect(row.get_by_role("button", name="Monitor")).to_be_visible(timeout=5000)
    finally:
        close_contest(live_server, organizer_token, contest["contest_id"])


def test_admin_can_transition_contest_status(
    admin_page: Page, live_server: str, organizer_token: str
):
    """The Transition dropdown in the admin table should close an ACTIVE contest."""
    contest = create_active_contest(live_server, organizer_token)
    try:
        admin_page.reload()
        admin_page.wait_for_load_state("networkidle")
        row = admin_page.locator("tr").filter(has_text=contest["name"])
        row.locator("select").select_option("CLOSED")
        expect(row.get_by_text("CLOSED")).to_be_visible(timeout=5000)
    finally:
        import requests
        requests.delete(
            f"{live_server}/api/v1/contests/{contest['contest_id']}",
            headers={"Authorization": f"Bearer {organizer_token}"},
        )


# ── User management ───────────────────────────────────────────────────────────

def test_admin_users_tab_shows_table(admin_page: Page):
    """The Users tab should list users in a table."""
    admin_page.get_by_role("button", name="Users").click()
    # The admin user should appear in the table cell.
    expect(admin_page.get_by_role("cell", name="admin", exact=True)).to_be_visible(timeout=5000)


def test_admin_can_create_new_user(admin_page: Page):
    """Filling in the New User form should create a user and show it in the list."""
    admin_page.get_by_role("button", name="Users").click()
    admin_page.get_by_role("button", name="New User").click()

    username = f"testuser_{uuid.uuid4().hex[:6]}"
    # The form uses <label> spans, not placeholders — locate by label text.
    admin_page.locator("form").filter(has_text="New User").get_by_label("Username").fill(username)
    admin_page.locator("form").filter(has_text="New User").get_by_label("Email").fill(f"{username}@test.com")
    admin_page.locator("form").filter(has_text="New User").get_by_label("Password").fill("Test1234!")
    admin_page.locator("form").filter(has_text="New User").get_by_role("button", name="Create").click()

    expect(admin_page.get_by_role("cell", name=username, exact=True)).to_be_visible(timeout=5000)


def test_admin_user_search_filters_list(admin_page: Page):
    """Typing in the search box should filter the user list to matching users."""
    admin_page.get_by_role("button", name="Users").click()
    search = admin_page.get_by_placeholder("Search username or email")
    search.fill("admin")
    expect(admin_page.get_by_role("cell", name="admin", exact=True)).to_be_visible(timeout=3000)


def test_admin_can_impersonate_organizer(
    admin_page: Page, live_server: str, organizer_token: str
):
    """Impersonating an organizer should switch the dashboard to the Organizer view."""
    admin_page.get_by_role("button", name="Users").click()
    admin_page.wait_for_selector("text=organizer_ui", timeout=5000)
    row = admin_page.locator("tr").filter(has_text="organizer_ui")
    row.get_by_role("button", name="Impersonate").click()
    expect(admin_page.get_by_text("Organizer Dashboard")).to_be_visible(timeout=5000)
    expect(admin_page.get_by_text("Impersonating")).to_be_visible(timeout=3000)
