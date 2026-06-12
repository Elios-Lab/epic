"""Unit tests for EPICClient."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from epic_client import EPICClient, EPICClientError, SubmissionNotOpenError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_client(server_url: str = "https://epic.example.com") -> EPICClient:
    return EPICClient(server_url)


def authenticated_client() -> EPICClient:
    client = make_client()
    client._token = "test-token"
    return client


class FakeWebSocket:
    """Proper async context-manager + async-iterable for testing stream()."""

    def __init__(self, *payloads: dict):
        self._payloads = payloads

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for p in self._payloads:
            yield json.dumps(p)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def test_trailing_slash_stripped():
    client = EPICClient("https://example.com/")
    assert client.server_url == "https://example.com/"  # urljoin needs trailing slash


def test_default_server_url():
    client = EPICClient()
    assert "epic.elioslab.net" in client.server_url


def test_token_starts_as_none():
    assert make_client()._token is None


# ---------------------------------------------------------------------------
# Authentication guard
# ---------------------------------------------------------------------------

def test_unauthenticated_submit_raises():
    client = make_client()
    with pytest.raises(RuntimeError, match="Not authenticated"):
        client.submit("cid", "forecasting", {"forecast": {}})


def test_unauthenticated_list_raises():
    client = make_client()
    with pytest.raises(RuntimeError, match="Not authenticated"):
        client.list_contests()


def test_unauthenticated_stream_raises():
    client = make_client()
    with pytest.raises(RuntimeError, match="Not authenticated"):
        # Calling __aiter__ triggers _require_token before the first yield.
        asyncio.run(client.stream("cid").__anext__())


# ---------------------------------------------------------------------------
# login()
# ---------------------------------------------------------------------------

def test_login_stores_token():
    client = make_client()
    with patch.object(client, "_request", return_value={"access_token": "tok123"}) as mock_req:
        result = client.login("alice", "secret")

    assert client._token == "tok123"
    assert result["access_token"] == "tok123"
    mock_req.assert_called_once_with(
        "POST",
        "/api/v1/auth/login",
        {"username": "alice", "password": "secret"},
        authenticated=False,
    )


# ---------------------------------------------------------------------------
# list_contests()
# ---------------------------------------------------------------------------

def test_list_contests_no_filter():
    client = authenticated_client()
    contests_data = [{"contest_id": "c1", "name": "Test"}]
    with patch.object(client, "_request", return_value={"contests": contests_data}) as mock_req:
        result = client.list_contests()

    assert result == contests_data
    mock_req.assert_called_once_with("GET", "/api/v1/contests?limit=100&offset=0")


def test_list_contests_with_status_filter():
    client = authenticated_client()
    with patch.object(client, "_request", return_value={"contests": []}) as mock_req:
        client.list_contests(status="ACTIVE")

    args = mock_req.call_args[0]
    assert "status=ACTIVE" in args[1]


def test_list_contests_with_visibility_and_pagination():
    client = authenticated_client()
    with patch.object(client, "_request", return_value={"contests": []}) as mock_req:
        client.list_contests(visibility="PUBLIC", limit=10, offset=20)

    args = mock_req.call_args[0]
    assert "visibility=PUBLIC" in args[1]
    assert "limit=10" in args[1]
    assert "offset=20" in args[1]


def test_list_contests_normalises_id_field():
    client = authenticated_client()
    # Server might return "id" instead of "contest_id" in some responses.
    with patch.object(client, "_request", return_value={"contests": [{"id": "c1"}]}):
        result = client.list_contests()

    assert result[0]["contest_id"] == "c1"


def test_list_contests_keeps_contest_id_when_present():
    client = authenticated_client()
    with patch.object(client, "_request", return_value={"contests": [{"contest_id": "c2", "id": "other"}]}):
        result = client.list_contests()

    assert result[0]["contest_id"] == "c2"


# ---------------------------------------------------------------------------
# get_contest() / get_task_spec()
# ---------------------------------------------------------------------------

def test_get_contest_normalises_id_field():
    client = authenticated_client()
    with patch.object(client, "_request", return_value={"id": "c1", "tasks": []}) as mock_req:
        result = client.get_contest("c1")

    assert result["contest_id"] == "c1"
    mock_req.assert_called_once_with("GET", "/api/v1/contests/c1")


def test_get_task_spec_extracts_forecasting_configuration():
    client = authenticated_client()
    contest = {
        "contest_id": "c1",
        "sampling_rate_hz": 10.0,
        "sensor_configs": [{"sensor_id": "position"}, {"sensor_id": "velocity"}],
        "tasks": [
            {
                "task_id": "t1",
                "task_type": "FORECASTING",
                "name": "FORECASTING",
                "weight": 1.0,
                "configuration": {
                    "eval_steps": 20,
                    "prediction_horizon_seconds": 2.0,
                    "target_variables": ["position"],
                    "score_against": "ground_truth",
                },
            }
        ],
    }
    with patch.object(client, "get_contest", return_value=contest):
        result = client.get_task_spec("c1")

    assert result["task_id"] == "t1"
    assert result["eval_steps"] == 20
    assert result["target_variables"] == ["position"]
    assert result["sensor_ids"] == ["position", "velocity"]
    assert result["sampling_rate_hz"] == 10.0


def test_get_task_spec_raises_when_missing():
    client = authenticated_client()
    contest = {"contest_id": "c1", "tasks": []}
    with patch.object(client, "get_contest", return_value=contest):
        with pytest.raises(RuntimeError, match="has no task"):
            client.get_task_spec("c1")


# ---------------------------------------------------------------------------
# register()
# ---------------------------------------------------------------------------

def test_register_success():
    client = authenticated_client()
    payload = {"registration_id": "r1", "status": "REGISTERED"}
    with patch.object(client, "_request", return_value=payload) as mock_req:
        result = client.register("c1")

    assert result == payload
    mock_req.assert_called_once_with("POST", "/api/v1/contest-registrations", {"contest_id": "c1"})


def test_register_already_registered_returns_gracefully():
    client = authenticated_client()
    with patch.object(client, "_request", side_effect=RuntimeError("Already registered for this contest")):
        result = client.register("c1")

    assert result["status"] == "REGISTERED"
    assert result["contest_id"] == "c1"


def test_register_propagates_other_errors():
    client = authenticated_client()
    with patch.object(client, "_request", side_effect=RuntimeError("Network error")):
        with pytest.raises(RuntimeError, match="Network error"):
            client.register("c1")


# ---------------------------------------------------------------------------
# submit()
# ---------------------------------------------------------------------------

def test_submit_sends_correct_body():
    client = authenticated_client()
    forecast = {"position": [0.1, 0.2, 0.3]}
    with patch.object(client, "_request", return_value={"submission_id": "s1"}) as mock_req:
        result = client.submit("c1", "forecasting", {"forecast": forecast})

    assert result["submission_id"] == "s1"
    mock_req.assert_called_once_with(
        "POST",
        "/api/v1/contests/c1/submissions",
        {"task_id": "forecasting", "payload": {"forecast": forecast}},
    )


def test_submit_does_not_include_prediction_from_sequence():
    client = authenticated_client()
    with patch.object(client, "_request", return_value={}) as mock_req:
        client.submit("c1", "forecasting", {"forecast": {}})

    body = mock_req.call_args[0][2]
    assert "prediction_from_sequence" not in body


# ---------------------------------------------------------------------------
# get_scores()
# ---------------------------------------------------------------------------

def test_get_scores_aggregates_per_submission():
    client = authenticated_client()
    submissions = [{"submission_id": "s1", "status": "EVALUATED"}]
    scores = {"scores": [{"metric_id": "mae", "value": 0.05}]}

    def side_effect(method, path, *args, **kwargs):
        if "submissions" in path and method == "GET" and path.endswith("submissions"):
            return {"submissions": submissions}
        return scores

    with patch.object(client, "_request", side_effect=side_effect):
        result = client.get_scores("c1")

    assert result["contest_id"] == "c1"
    assert result["submissions"][0]["submission_id"] == "s1"
    assert result["submissions"][0]["scores"][0]["metric_id"] == "mae"


# ---------------------------------------------------------------------------
# get_leaderboard()
# ---------------------------------------------------------------------------

def test_get_leaderboard_returns_raw_response():
    client = authenticated_client()
    lb = {"entries": [{"rank": 1, "user_id": "u1", "score": 0.01}]}
    with patch.object(client, "_request", return_value=lb) as mock_req:
        result = client.get_leaderboard("c1")

    assert result == lb
    mock_req.assert_called_once_with("GET", "/api/v1/contests/c1/leaderboard")


# ---------------------------------------------------------------------------
# stream() — async generator
# ---------------------------------------------------------------------------

_EVAL_STARTED = {"event": "evaluation_started", "observation_end_sequence_id": 0, "evaluation_steps": 0}


async def test_stream_yields_observations():
    client = authenticated_client()
    obs1 = {
        "sequence_id": 1,
        "committed_through": 0,
        "timestamp": "2027-01-01T00:00:00Z",
        "sensors": {"pos": 0.1},
    }
    obs2 = {"sequence_id": 2, "timestamp": "2027-01-01T00:00:01Z", "sensors": {"pos": 0.2}}

    with patch("websockets.connect", return_value=FakeWebSocket(obs1, obs2, _EVAL_STARTED)):
        collected = [o async for o in client.stream("c1")]

    assert len(collected) == 2
    assert collected[0]["sequence_id"] == 1
    assert collected[0]["committed_through"] == 0
    assert collected[1]["sensors"]["pos"] == 0.2


async def test_stream_stops_on_evaluation_started():
    client = authenticated_client()
    obs = {"sequence_id": 1, "timestamp": "T", "sensors": {"pos": 0.1}}
    eval_event = {"event": "evaluation_started", "observation_end_sequence_id": 1, "evaluation_steps": 10}

    with patch("websockets.connect", return_value=FakeWebSocket(obs, eval_event)):
        collected = [o async for o in client.stream("c1")]

    assert len(collected) == 1
    assert collected[0]["sequence_id"] == 1


async def test_stream_evaluation_started_only_no_crash():
    """A stream that sends only the phase-change event must not crash."""
    client = authenticated_client()

    with patch("websockets.connect", return_value=FakeWebSocket(_EVAL_STARTED)):
        collected = [o async for o in client.stream("c1")]

    assert collected == []


async def test_stream_can_include_control_events():
    client = authenticated_client()
    obs = {"sequence_id": 1, "timestamp": "T", "sensors": {"pos": 0.1}}

    with patch("websockets.connect", return_value=FakeWebSocket(obs, _EVAL_STARTED)):
        collected = [o async for o in client.stream("c1", include_events=True)]

    assert collected[0]["sequence_id"] == 1
    assert collected[1]["event"] == "evaluation_started"
    assert collected[1]["evaluation_steps"] == 0


async def test_stream_stops_on_contest_closed_event():
    client = authenticated_client()
    obs = {"sequence_id": 1, "timestamp": "T", "sensors": {"pos": 0.1}}

    with patch("websockets.connect", return_value=FakeWebSocket(obs, {"event": "contest_closed"})):
        collected = [o async for o in client.stream("c1")]

    assert collected == [obs]


async def test_stream_raises_on_first_connection_failure():
    client = authenticated_client()

    with patch("websockets.connect", side_effect=OSError("refused")):
        with pytest.raises(RuntimeError, match="Could not connect"):
            async for _ in client.stream("c1"):
                pass


async def test_stream_reconnects_after_clean_close():
    """After a clean close without evaluation_started, the stream reconnects."""
    client = authenticated_client()
    obs1 = {"sequence_id": 1, "timestamp": "T", "sensors": {"pos": 0.0}}
    obs2 = {"sequence_id": 2, "timestamp": "T", "sensors": {"pos": 1.0}}
    connect_calls = 0

    def connect_factory(*args, **kwargs):
        nonlocal connect_calls
        connect_calls += 1
        if connect_calls == 1:
            return FakeWebSocket(obs1)                             # closes cleanly
        return FakeWebSocket(obs2, {"event": "evaluation_started"})  # ends stream

    with patch("websockets.connect", side_effect=connect_factory):
        with patch("epic_client.client.asyncio.sleep", new=AsyncMock()):
            collected = [o async for o in client.stream("c1")]

    assert len(collected) == 2
    assert collected[0]["sequence_id"] == 1
    assert collected[1]["sequence_id"] == 2
    assert connect_calls == 2


# ---------------------------------------------------------------------------
# collect()
# ---------------------------------------------------------------------------

def _make_stream(*observations: dict):
    """Return an async generator that yields the given observations."""
    async def _gen(contest_id):
        for obs in observations:
            yield obs
    return _gen


async def test_collect_returns_list_of_observations():
    client = authenticated_client()
    obs = {"sequence_id": 1, "timestamp": "T", "sensors": {"pos": 0.5}}

    with patch.object(client, "stream", _make_stream(obs)):
        result = await client.collect("c1", duration_seconds=5)

    assert result == [obs]


async def test_collect_stops_when_stream_ends():
    """collect() must terminate when the stream ends via evaluation_started."""
    client = authenticated_client()
    obs = {"sequence_id": 1, "timestamp": "T", "sensors": {"pos": 0.5}}

    with patch("websockets.connect", return_value=FakeWebSocket(obs, _EVAL_STARTED)):
        result = await client.collect("c1", duration_seconds=60)

    assert len(result) == 1


async def test_collect_writes_csv(tmp_path):
    client = authenticated_client()
    obs = {
        "sequence_id": 7,
        "timestamp": "2027-01-01T00:00:07Z",
        "sensors": {"pos": 0.7, "vel": 1.2},
    }

    with patch.object(client, "stream", _make_stream(obs)):
        csv_file = tmp_path / "out.csv"
        await client.collect("c1", duration_seconds=5, csv_path=csv_file)

    lines = csv_file.read_text().splitlines()
    assert lines[0] == "sequence_id,timestamp,pos,vel"
    assert "7" in lines[1]
    assert "2027-01-01T00:00:07Z" in lines[1]
    assert "0.7" in lines[1]


# ---------------------------------------------------------------------------
# _request() internals
# ---------------------------------------------------------------------------

def test_request_raises_runtime_error_on_http_error():
    from urllib.error import HTTPError
    import io

    client = authenticated_client()
    err = HTTPError(url="u", code=422, msg="Unprocessable", hdrs={}, fp=io.BytesIO(b'{"detail":"bad"}'))

    with patch("epic_client.client.urlopen", side_effect=err):
        with pytest.raises(RuntimeError, match="422"):
            client._request("POST", "/api/v1/contests/x/submissions", {})


def test_request_parses_standard_epic_error():
    from urllib.error import HTTPError
    import io

    client = authenticated_client()
    body = b'{"error":{"code":"SUBMISSION_ERROR","message":"Payload is invalid"}}'
    err = HTTPError(url="u", code=422, msg="Unprocessable", hdrs={}, fp=io.BytesIO(body))

    with patch("epic_client.client.urlopen", side_effect=err):
        with pytest.raises(EPICClientError) as exc_info:
            client._request("POST", "/api/v1/contests/x/submissions", {})

    assert exc_info.value.status_code == 422
    assert exc_info.value.error_code == "SUBMISSION_ERROR"
    assert str(exc_info.value) == "EPIC API request failed: 422 Payload is invalid"


def test_request_raises_submission_not_open_error():
    from urllib.error import HTTPError
    import io

    client = authenticated_client()
    message = (
        "Submissions are not yet accepted — the evaluation phase has not ended. "
        "Submissions open at 2026-06-14T13:06:00+00:00"
    )
    body = json.dumps({
        "error": {
            "code": "CONTEST_STATE_ERROR",
            "message": message,
        }
    }).encode("utf-8")
    err = HTTPError(url="u", code=409, msg="Conflict", hdrs={}, fp=io.BytesIO(body))

    with patch("epic_client.client.urlopen", side_effect=err):
        with pytest.raises(SubmissionNotOpenError) as exc_info:
            client.submit("c1", "forecasting", {"forecast": {}})

    assert exc_info.value.status_code == 409
    assert exc_info.value.error_code == "CONTEST_STATE_ERROR"
    assert exc_info.value.opens_at == "2026-06-14T13:06:00+00:00"
    assert str(exc_info.value) == message


def test_request_raises_runtime_error_on_url_error():
    from urllib.error import URLError

    client = authenticated_client()
    with patch("epic_client.client.urlopen", side_effect=URLError("no route")):
        with pytest.raises(RuntimeError, match="no route"):
            client._request("GET", "/api/v1/contests")


def test_request_returns_empty_dict_on_no_content():
    resp = MagicMock()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    resp.read.return_value = b""

    client = authenticated_client()
    with patch("epic_client.client.urlopen", return_value=resp):
        result = client._request("DELETE", "/api/v1/contests/c1")

    assert result == {}
