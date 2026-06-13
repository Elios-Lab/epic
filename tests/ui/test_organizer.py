"""UI tests for the Organizer dashboard."""

import time

import pytest
from playwright.sync_api import Page, expect

from tests.ui.conftest import close_contest, create_active_contest


def _open_organizer_dashboard(page: Page):
    page.wait_for_selector("text=Organizer Dashboard", timeout=5000)


def _open_new_contest_tab(page: Page):
    page.get_by_role("button", name="New Contest").click()


# ── Contest listing ───────────────────────────────────────────────────────────

def test_organizer_dashboard_loads(page: Page):
    """Organizer should land on their dashboard."""
    _open_organizer_dashboard(page)
    expect(page.get_by_text("Organizer Dashboard")).to_be_visible()


def test_organizer_sees_own_contests(
    page: Page, live_server: str, organizer_token: str
):
    """An organizer's contest should appear in their contest list."""
    contest = create_active_contest(live_server, organizer_token)
    try:
        page.reload()
        page.wait_for_load_state("networkidle")
        _open_organizer_dashboard(page)
        expect(page.get_by_text(contest["name"])).to_be_visible(timeout=5000)
    finally:
        close_contest(live_server, organizer_token, contest["contest_id"])


def test_contest_card_shows_status_badge(
    page: Page, live_server: str, organizer_token: str
):
    """An ACTIVE contest card should display the ACTIVE badge."""
    contest = create_active_contest(live_server, organizer_token)
    try:
        page.reload()
        page.wait_for_load_state("networkidle")
        card = page.locator("article").filter(has_text=contest["name"])
        expect(card.get_by_text("ACTIVE")).to_be_visible(timeout=5000)
    finally:
        close_contest(live_server, organizer_token, contest["contest_id"])


def test_contest_card_shows_phase_badge(
    page: Page, live_server: str, organizer_token: str
):
    """An ACTIVE two-phase contest should show the Observation phase badge."""
    contest = create_active_contest(live_server, organizer_token)
    try:
        page.reload()
        page.wait_for_load_state("networkidle")
        card = page.locator("article").filter(has_text=contest["name"])
        expect(card.get_by_text("Observation")).to_be_visible(timeout=5000)
    finally:
        close_contest(live_server, organizer_token, contest["contest_id"])


# ── Contest lifecycle ─────────────────────────────────────────────────────────

def test_organizer_can_pause_active_contest(
    page: Page, live_server: str, organizer_token: str
):
    """Clicking Pause should transition the contest to PAUSED."""
    contest = create_active_contest(live_server, organizer_token)
    try:
        page.reload()
        page.wait_for_load_state("networkidle")
        card = page.locator("article").filter(has_text=contest["name"])
        card.get_by_role("button", name="Pause").click()
        expect(card.get_by_text("PAUSED")).to_be_visible(timeout=5000)
    finally:
        close_contest(live_server, organizer_token, contest["contest_id"])


def test_organizer_can_resume_paused_contest(
    page: Page, live_server: str, organizer_token: str
):
    """A PAUSED contest should show a Resume button that transitions it back to ACTIVE."""
    contest = create_active_contest(live_server, organizer_token)
    try:
        page.reload()
        page.wait_for_load_state("networkidle")
        card = page.locator("article").filter(has_text=contest["name"])
        card.get_by_role("button", name="Pause").click()
        expect(card.get_by_text("PAUSED")).to_be_visible(timeout=5000)
        card.get_by_role("button", name="Resume").click()
        expect(card.get_by_text("ACTIVE")).to_be_visible(timeout=5000)
    finally:
        close_contest(live_server, organizer_token, contest["contest_id"])


def test_organizer_can_close_contest(
    page: Page, live_server: str, organizer_token: str
):
    """Clicking Close should transition the contest to CLOSED."""
    contest = create_active_contest(live_server, organizer_token)
    page.reload()
    page.wait_for_load_state("networkidle")
    card = page.locator("article").filter(has_text=contest["name"])
    card.get_by_role("button", name="Close").click()
    expect(card.get_by_text("CLOSED")).to_be_visible(timeout=5000)
    # Clean up — contest is already closed, just delete it.
    import requests
    requests.delete(
        f"{live_server}/api/v1/contests/{contest['contest_id']}",
        headers={"Authorization": f"Bearer {organizer_token}"},
    )


def test_organizer_can_delete_draft_contest(
    page: Page, live_server: str, organizer_token: str
):
    """A DRAFT contest should have a Delete button that removes it."""
    import requests
    headers = {"Authorization": f"Bearer {organizer_token}"}
    from datetime import datetime, timedelta, timezone
    import uuid
    now = datetime.now(timezone.utc)
    resp = requests.post(
        f"{live_server}/api/v1/contests",
        json={
            "name": f"Draft to delete {uuid.uuid4().hex[:6]}",
            "description": "x", "visibility": "PUBLIC",
            "twin_id": "mass_spring_damper",
            "sensor_configs": [{"sensor_id": "position"}],
            "fault_schedule": [], "initial_conditions": {"position": 0.1, "velocity": 0.0},
            "sampling_rate_hz": 10.0,
            "start_date": now.isoformat(),
            "end_of_observation": (now + timedelta(hours=1)).isoformat(),
            "prediction_horizon_seconds": 60,
            "end_date": (now + timedelta(hours=2)).isoformat(),
            "task_type": "FORECASTING", "metric_ids": ["mae"], "score_against": "ground_truth",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    contest = resp.json()

    page.reload()
    page.wait_for_load_state("networkidle")
    card = page.locator("article").filter(has_text=contest["name"])
    expect(card).to_be_visible(timeout=5000)
    card.get_by_role("button", name="Delete").click()
    # Confirm the deletion in the modal.
    page.get_by_role("button", name="Delete").last.click()
    expect(card).to_be_hidden(timeout=5000)


# ── Contest creation ──────────────────────────────────────────────────────────

def test_organizer_new_contest_tab_shows_templates(page: Page):
    """The New Contest tab should list available templates."""
    _open_organizer_dashboard(page)
    _open_new_contest_tab(page)
    expect(page.get_by_text("Choose a Template")).to_be_visible(timeout=3000)
    # At least one template card should be visible.
    expect(page.locator("button").filter(has_text="mass_spring_damper").first).to_be_visible(timeout=3000)


def test_selecting_template_shows_form(page: Page):
    """Selecting a template should advance to the creation form."""
    _open_organizer_dashboard(page)
    _open_new_contest_tab(page)
    page.locator("button").filter(has_text="mass_spring_damper").first.click()
    expect(page.get_by_text("Create Contest")).to_be_visible(timeout=3000)
    expect(page.get_by_role("textbox", name="Start date")).to_be_visible()


def test_sensor_checkboxes_loaded_from_catalog(page: Page):
    """After selecting a template the sensor list should be populated."""
    _open_organizer_dashboard(page)
    _open_new_contest_tab(page)
    page.locator("button").filter(has_text="mass_spring_damper").first.click()
    page.wait_for_selector("text=Sensors", timeout=5000)
    # At least one sensor checkbox should appear.
    expect(page.locator("input[type='checkbox']").first).to_be_visible(timeout=5000)


def test_create_contest_form_submits_successfully(
    page: Page, live_server: str, organizer_token: str
):
    """Filling in the form and clicking Create should produce a new DRAFT contest."""
    import uuid
    _open_organizer_dashboard(page)
    _open_new_contest_tab(page)
    page.locator("button").filter(has_text="mass_spring_damper").first.click()
    page.wait_for_selector("text=Create Contest", timeout=5000)

    name = f"UI Created {uuid.uuid4().hex[:6]}"
    page.get_by_label("Contest name").fill(name)
    page.get_by_role("button", name="Create").click()

    # Should return to the Contests tab and show the new contest.
    expect(page.get_by_text(name)).to_be_visible(timeout=10000)

    # Clean up via API.
    import requests
    resp = requests.get(f"{live_server}/api/v1/contests", headers={"Authorization": f"Bearer {organizer_token}"})
    for c in resp.json().get("contests", []):
        if c["name"] == name:
            requests.delete(f"{live_server}/api/v1/contests/{c['contest_id']}", headers={"Authorization": f"Bearer {organizer_token}"})
            break


# ── Participant management ───────────────────────────────────────────────────

def test_organizer_can_send_participant_invitation(
    page: Page, live_server: str, organizer_token: str
):
    """The contest detail panel should send invitation emails and list them."""
    import uuid

    contest = create_active_contest(live_server, organizer_token)
    email = f"invite_{uuid.uuid4().hex[:6]}@test.com"
    try:
        page.reload()
        page.wait_for_load_state("networkidle")
        card = page.locator("article").filter(has_text=contest["name"])
        card.get_by_text(contest["name"]).click()
        card.get_by_placeholder("anna@example.com").fill(email)
        card.get_by_role("button", name="Send invitations").click()

        expect(card.get_by_text(email)).to_be_visible(timeout=5000)
        expect(card.get_by_text("Pending")).to_be_visible(timeout=5000)
    finally:
        close_contest(live_server, organizer_token, contest["contest_id"])


def test_organizer_can_list_and_remove_registered_participant(
    page: Page, live_server: str, organizer_token: str, participant_token: str
):
    """A contest owner should see registered participants and remove them."""
    import requests

    contest = create_active_contest(live_server, organizer_token)
    try:
        registration = requests.post(
            f"{live_server}/api/v1/contest-registrations",
            json={"contest_id": contest["contest_id"]},
            headers={"Authorization": f"Bearer {participant_token}"},
        )
        assert registration.status_code == 201

        page.reload()
        page.wait_for_load_state("networkidle")
        card = page.locator("article").filter(has_text=contest["name"])
        card.get_by_text(contest["name"]).click()

        expect(card.get_by_text("participant_ui")).to_be_visible(timeout=5000)
        expect(card.get_by_text("part@test.com")).to_be_visible(timeout=5000)
        card.get_by_role("button", name="Remove").click()
        expect(card.get_by_text("BANNED")).to_be_visible(timeout=5000)
    finally:
        close_contest(live_server, organizer_token, contest["contest_id"])
