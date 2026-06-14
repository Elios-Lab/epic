"""
Playwright tests for the Monitor component in the organizer dashboard.

Each test creates a real ACTIVE contest, drives the browser to interact
with the Monitor button, and asserts on visible DOM state.
"""

import time

import pytest
from playwright.sync_api import Page, expect

from tests.ui.conftest import close_contest, create_active_contest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _open_organizer_contests(page: Page, live_server: str):
    """Navigate to the Organizer dashboard → Contests tab."""
    page.goto(live_server)
    page.wait_for_load_state("networkidle")
    # The app routes by role; the organizer lands on their dashboard.
    page.wait_for_selector("text=Organizer Dashboard", timeout=5000)


def _monitor_button(page: Page, contest_name: str):
    """Return the Monitor button inside the contest card with the given name."""
    card = page.locator("article").filter(has_text=contest_name)
    return card.get_by_role("button", name="Monitor")


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_monitor_button_visible_for_active_contest(
    page: Page, live_server: str, organizer_token: str
):
    """Monitor button should appear on ACTIVE contest cards."""
    contest = create_active_contest(live_server, organizer_token)
    try:
        _open_organizer_contests(page, live_server)
        btn = _monitor_button(page, contest["name"])
        expect(btn).to_be_visible()
    finally:
        close_contest(live_server, organizer_token, contest["contest_id"])


def test_clicking_monitor_shows_chart_panel(
    page: Page, live_server: str, organizer_token: str
):
    """Clicking Monitor should show the chart panel with the contest name."""
    contest = create_active_contest(live_server, organizer_token)
    try:
        _open_organizer_contests(page, live_server)
        _monitor_button(page, contest["name"]).click()

        # Chart container should become visible.
        chart_panel = page.locator("canvas#monitorChartOrganizer").locator("..")
        expect(chart_panel).to_be_visible(timeout=3000)

        # Contest name shown in the monitor header.
        expect(page.locator(f"text={contest['name']}").first).to_be_visible()
    finally:
        close_contest(live_server, organizer_token, contest["contest_id"])


def test_canvas_has_nonzero_dimensions_after_monitor_start(
    page: Page, live_server: str, organizer_token: str
):
    """Canvas must have real pixel dimensions — this was the root cause of the
    Chart.js fullSize crash."""
    contest = create_active_contest(live_server, organizer_token)
    try:
        _open_organizer_contests(page, live_server)
        _monitor_button(page, contest["name"]).click()

        # Wait for Chart.js to initialize (createMonitorChart retries until
        # offsetWidth > 0, so we allow a generous timeout).
        time.sleep(0.5)

        canvas = page.locator("canvas#monitorChartOrganizer")
        dimensions = canvas.evaluate(
            "el => ({ w: el.offsetWidth, h: el.offsetHeight })"
        )
        assert dimensions["w"] > 0, "Canvas width must be > 0"
        assert dimensions["h"] > 0, "Canvas height must be > 0"
    finally:
        close_contest(live_server, organizer_token, contest["contest_id"])


def test_stream_delivers_data_points_to_chart(
    page: Page, live_server: str, organizer_token: str
):
    """After a few seconds the chart should contain at least one dataset with
    data points — confirming the full WebSocket → Chart pipeline works."""
    contest = create_active_contest(live_server, organizer_token)
    try:
        _open_organizer_contests(page, live_server)
        _monitor_button(page, contest["name"]).click()

        # Wait for data to arrive (contest runs at 10 Hz, so 2 s → ~20 points).
        time.sleep(2.5)

        dataset_length = page.evaluate("""
            () => {
                const charts = Object.values(Chart.instances);
                if (!charts.length) return 0;
                const datasets = charts[0].data.datasets;
                if (!datasets.length) return 0;
                return datasets[0].data.length;
            }
        """)
        assert dataset_length > 0, (
            f"Expected chart data points after stream, got {dataset_length}"
        )
    finally:
        close_contest(live_server, organizer_token, contest["contest_id"])


def test_no_console_errors_during_streaming(
    page: Page, live_server: str, organizer_token: str
):
    """No JavaScript errors should appear in the console during normal streaming
    (catches the Chart.js fullSize / stack-overflow regressions)."""
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

    contest = create_active_contest(live_server, organizer_token)
    try:
        _open_organizer_contests(page, live_server)
        _monitor_button(page, contest["name"]).click()
        time.sleep(2.5)  # observe for 2.5 s at 10 Hz

        assert errors == [], f"Unexpected JS errors during streaming: {errors}"
    finally:
        close_contest(live_server, organizer_token, contest["contest_id"])


def test_stop_monitor_hides_chart_panel(
    page: Page, live_server: str, organizer_token: str
):
    """Clicking Stop should hide the chart panel and close the WebSocket."""
    contest = create_active_contest(live_server, organizer_token)
    try:
        _open_organizer_contests(page, live_server)
        _monitor_button(page, contest["name"]).click()
        time.sleep(0.5)

        # Stop the monitor — use exact match to avoid hitting "Stop Monitor".
        page.get_by_role("button", name="Stop", exact=True).click()

        # Chart panel should no longer be visible.
        chart_panel = page.locator("canvas#monitorChartOrganizer").locator("..")
        expect(chart_panel).to_be_hidden(timeout=2000)

        # Monitor button label reverts to "Monitor".
        btn = _monitor_button(page, contest["name"])
        expect(btn).to_have_text("Monitor")
    finally:
        close_contest(live_server, organizer_token, contest["contest_id"])


def test_monitor_button_label_toggles(
    page: Page, live_server: str, organizer_token: str
):
    """Button label should switch between 'Monitor' and 'Stop Monitor'."""
    contest = create_active_contest(live_server, organizer_token)
    try:
        _open_organizer_contests(page, live_server)
        btn = _monitor_button(page, contest["name"])

        expect(btn).to_have_text("Monitor")
        btn.click()
        expect(btn).to_have_text("Stop Monitor", timeout=2000)
        btn.click()
        expect(btn).to_have_text("Monitor", timeout=2000)
    finally:
        close_contest(live_server, organizer_token, contest["contest_id"])


def test_error_banner_on_stream_disconnect(
    page: Page, live_server: str, organizer_token: str
):
    """Closing the contest while the monitor is active should show the
    disconnect error banner."""
    import requests
    contest = create_active_contest(live_server, organizer_token)
    try:
        _open_organizer_contests(page, live_server)
        _monitor_button(page, contest["name"]).click()
        time.sleep(0.5)

        # Close the contest — the engine detects this every commit_interval
        # (10 steps = 1 s at 10 Hz), broadcasts "contest_closed", and the
        # WebSocket closes cleanly.
        headers = {"Authorization": f"Bearer {organizer_token}"}
        requests.patch(
            f"{live_server}/api/v1/contests/{contest['contest_id']}",
            json={"status": "CLOSED"},
            headers=headers,
        )

        # An amber error banner should appear within ~3 s (1 s engine poll +
        # network round-trip + browser render).
        error_banner = page.locator(".bg-amber-50")
        expect(error_banner).to_be_visible(timeout=6000)
        expect(error_banner).not_to_be_empty()
    finally:
        close_contest(live_server, organizer_token, contest["contest_id"])
