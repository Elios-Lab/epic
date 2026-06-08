"""UI tests for the Participant dashboard."""

import time

import pytest
from playwright.sync_api import Page, expect

from tests.ui.conftest import close_contest, create_active_contest


def _login_as(page: Page, live_server: str, username: str, password: str):
    page.goto(live_server)
    page.wait_for_load_state("networkidle")
    page.get_by_role("link", name="Log in").click()
    page.get_by_placeholder("Username").fill(username)
    page.get_by_placeholder("Password").fill(password)
    page.get_by_role("button", name="Log in").click()


@pytest.fixture
def participant_page(browser_context, live_server, participant_token):
    """Open a fresh page logged in as the participant."""
    pg = browser_context.new_page()
    pg.goto(live_server)
    pg.evaluate(f"() => localStorage.setItem('epic_token', '{participant_token}')")
    pg.reload()
    pg.wait_for_load_state("networkidle")
    yield pg
    pg.close()


def test_participant_dashboard_loads(
    participant_page: Page, live_server: str
):
    """Participant should see their dashboard after login."""
    expect(participant_page.get_by_text("Participant Dashboard")).to_be_visible(timeout=5000)


def test_participant_sees_active_contest(
    participant_page: Page, live_server: str, organizer_token: str
):
    """An ACTIVE contest should appear in the participant's contest list."""
    contest = create_active_contest(live_server, organizer_token)
    try:
        participant_page.reload()
        participant_page.wait_for_load_state("networkidle")
        expect(participant_page.get_by_text(contest["name"])).to_be_visible(timeout=5000)
    finally:
        close_contest(live_server, organizer_token, contest["contest_id"])


def test_participant_can_register_for_contest(
    participant_page: Page, live_server: str, organizer_token: str
):
    """Clicking Register should register the participant and show a Connect button."""
    contest = create_active_contest(live_server, organizer_token)
    try:
        participant_page.reload()
        participant_page.wait_for_load_state("networkidle")
        card = participant_page.locator("article").filter(has_text=contest["name"])
        register_btn = card.get_by_role("button", name="Register")
        expect(register_btn).to_be_visible(timeout=5000)
        register_btn.click()
        expect(card.get_by_role("button", name="Connect")).to_be_visible(timeout=5000)
    finally:
        close_contest(live_server, organizer_token, contest["contest_id"])


def test_participant_can_connect_and_see_stream(
    participant_page: Page, live_server: str, organizer_token: str
):
    """Connecting to a contest should show the live sensor stream view."""
    contest = create_active_contest(live_server, organizer_token)
    try:
        participant_page.reload()
        participant_page.wait_for_load_state("networkidle")
        card = participant_page.locator("article").filter(has_text=contest["name"])
        card.get_by_role("button", name="Register").click()
        card.get_by_role("button", name="Connect").click(timeout=5000)
        expect(participant_page.get_by_text("Live stream from")).to_be_visible(timeout=5000)
    finally:
        close_contest(live_server, organizer_token, contest["contest_id"])
