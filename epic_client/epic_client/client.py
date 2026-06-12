"""Participant client for EPIC contests."""

from __future__ import annotations

import asyncio
import csv
import json
import re
import time
from pathlib import Path
from typing import AsyncIterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen


class EPICClientError(RuntimeError):
    """Raised when the EPIC API returns an error response."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        error_code: str | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.response_body = response_body


class SubmissionNotOpenError(EPICClientError):
    """Raised when a forecast is submitted before the submission window opens."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        error_code: str | None = None,
        response_body: str | None = None,
        opens_at: str | None = None,
    ) -> None:
        super().__init__(
            status_code,
            message,
            error_code=error_code,
            response_body=response_body,
        )
        self.opens_at = opens_at


class EPICClient:
    def __init__(self, server_url: str = "https://epic.elioslab.net") -> None:
        self.server_url = server_url.rstrip("/") + "/"
        self._token: str | None = None

    def login(self, username: str, password: str) -> dict:
        response = self._request(
            "POST",
            "/api/v1/auth/login",
            {"username": username, "password": password},
            authenticated=False,
        )
        self._token = response["access_token"]
        return response

    def register(self, contest_id: str) -> dict:
        try:
            return self._request(
                "POST",
                "/api/v1/contest-registrations",
                {"contest_id": contest_id},
            )
        except RuntimeError as exc:
            if "Already registered for this contest" not in str(exc):
                raise
            return {
                "contest_id": contest_id,
                "status": "REGISTERED",
                "message": "Already registered for this contest",
            }

    def list_contests(
        self,
        status: str | None = None,
        visibility: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        params = {"limit": limit, "offset": offset}
        if status is not None:
            params["status"] = status
        if visibility is not None:
            params["visibility"] = visibility
        query = f"?{urlencode(params)}"
        response = self._request("GET", f"/api/v1/contests{query}")
        contests = response["contests"]
        for contest in contests:
            self._normalize_contest(contest)
        return contests

    def get_contest(self, contest_id: str) -> dict:
        contest = self._request("GET", f"/api/v1/contests/{contest_id}")
        return self._normalize_contest(contest)

    def get_task_spec(self, contest_id: str, task_type: str = "FORECASTING") -> dict:
        contest = self.get_contest(contest_id)
        requested = task_type.upper()
        task = next(
            (
                task
                for task in contest.get("tasks", [])
                if task.get("task_type", "").upper() == requested
                or task.get("task_id") == task_type
            ),
            None,
        )
        if task is None:
            raise RuntimeError(
                f"Contest '{contest_id}' has no task matching '{task_type}'."
            )

        configuration = task.get("configuration") or {}
        spec = {
            **task,
            "contest_id": contest["contest_id"],
            "configuration": configuration,
            "sampling_rate_hz": contest.get("sampling_rate_hz"),
            "sensor_ids": [
                sensor["sensor_id"]
                for sensor in contest.get("sensor_configs", [])
                if "sensor_id" in sensor
            ],
        }
        for key in (
            "eval_steps",
            "prediction_horizon_seconds",
            "score_against",
            "target_variables",
        ):
            if key in configuration:
                spec[key] = configuration[key]
        return spec

    async def stream(
        self,
        contest_id: str,
        *,
        include_events: bool = False,
    ) -> AsyncIterator[dict]:
        self._require_token()
        websocket_url = self._websocket_url(f"/api/v1/ws/contests/{contest_id}")
        reconnect_delay = 1.0
        first_attempt = True

        while True:
            try:
                import websockets

                async with websockets.connect(websocket_url) as websocket:
                    first_attempt = False
                    async for message in websocket:
                        payload = json.loads(message)
                        event = payload.get("event")
                        if event is not None:
                            if include_events:
                                yield payload
                            if event in {"evaluation_started", "contest_closed"}:
                                return
                            continue
                        yield self._normalize_observation(payload)
                # Clean close without evaluation_started — reconnect.
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if first_attempt:
                    raise RuntimeError(
                        f"Could not connect to contest stream: {exc}"
                    ) from exc
            await asyncio.sleep(reconnect_delay)

    async def collect(
        self,
        contest_id: str,
        duration_seconds: float,
        csv_path: str | Path | None = None,
    ) -> list[dict]:
        observations: list[dict] = []
        deadline = time.monotonic() + duration_seconds
        writer: csv.DictWriter | None = None
        csv_file = None

        if csv_path is not None:
            csv_file = Path(csv_path).open("w", newline="")

        try:
            stream = self.stream(contest_id).__aiter__()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    observation = await asyncio.wait_for(stream.__anext__(), remaining)
                except asyncio.TimeoutError:
                    break
                except StopAsyncIteration:
                    break
                observations.append(observation)
                if csv_file is not None:
                    if writer is None:
                        writer = csv.DictWriter(
                            csv_file,
                            fieldnames=[
                                "sequence_id",
                                "timestamp",
                                *sorted(observation["sensors"]),
                            ],
                            extrasaction="ignore",
                        )
                        writer.writeheader()
                    writer.writerow(self._csv_row(observation))
        finally:
            if csv_file is not None:
                csv_file.close()

        return observations

    def submit(
        self,
        contest_id: str,
        task_id: str,
        payload: dict,
    ) -> dict:
        return self._request(
            "POST",
            f"/api/v1/contests/{contest_id}/submissions",
            {
                "task_id": task_id,
                "payload": payload,
            },
        )

    def get_scores(self, contest_id: str) -> dict:
        submissions = self._request(
            "GET", f"/api/v1/contests/{contest_id}/submissions"
        )["submissions"]
        scored_submissions = []
        for submission in submissions:
            scores = self._request(
                "GET", f"/api/v1/submissions/{submission['submission_id']}/scores"
            )
            scored_submissions.append({**submission, "scores": scores["scores"]})
        return {"contest_id": contest_id, "submissions": scored_submissions}

    def get_leaderboard(self, contest_id: str) -> dict:
        return self._request("GET", f"/api/v1/contests/{contest_id}/leaderboard")

    def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        authenticated: bool = True,
    ) -> dict:
        if authenticated:
            self._require_token()

        data = None
        headers = {"Content-Type": "application/json"}
        if authenticated and self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        request = Request(
            urljoin(self.server_url, path.lstrip("/")),
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request) as response:
                response_body = response.read()
        except HTTPError as exc:
            response_text = exc.read().decode("utf-8")
            raise self._api_error(exc.code, response_text) from exc
        except URLError as exc:
            raise RuntimeError(f"EPIC API request failed: {exc.reason}") from exc

        if not response_body:
            return {}
        return json.loads(response_body.decode("utf-8"))

    def _require_token(self) -> None:
        if self._token is None:
            raise RuntimeError("Not authenticated. Call login() first.")

    def _api_error(self, status_code: int, response_text: str) -> EPICClientError:
        error_code = None
        message = response_text
        try:
            payload = json.loads(response_text)
        except json.JSONDecodeError:
            payload = None

        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                error_code = error.get("code")
                message = error.get("message") or response_text

        if (
            status_code == 409
            and error_code == "CONTEST_STATE_ERROR"
            and "Submissions are not yet accepted" in message
        ):
            return SubmissionNotOpenError(
                status_code,
                message,
                error_code=error_code,
                response_body=response_text,
                opens_at=self._extract_opens_at(message),
            )

        return EPICClientError(
            status_code,
            f"EPIC API request failed: {status_code} {message}",
            error_code=error_code,
            response_body=response_text,
        )

    def _extract_opens_at(self, message: str) -> str | None:
        match = re.search(r"Submissions open at (\S+)", message)
        return match.group(1) if match else None

    def _normalize_contest(self, contest: dict) -> dict:
        if "contest_id" not in contest and "id" in contest:
            contest["contest_id"] = contest["id"]
        return contest

    def _normalize_observation(self, payload: dict) -> dict:
        observation = {
            "sequence_id": payload["sequence_id"],
            "timestamp": payload["timestamp"],
            "sensors": payload["sensors"],
        }
        for key in ("session_id", "committed_through"):
            if key in payload:
                observation[key] = payload[key]
        return observation

    def _csv_row(self, observation: dict) -> dict:
        return {
            "sequence_id": observation["sequence_id"],
            "timestamp": observation["timestamp"],
            **observation["sensors"],
        }

    def _websocket_url(self, path: str) -> str:
        self._require_token()
        parsed = urlparse(urljoin(self.server_url, path.lstrip("/")))
        scheme = "wss" if parsed.scheme == "https" else "ws"
        query = urlencode({"token": self._token})
        return urlunparse((scheme, parsed.netloc, parsed.path, "", query, ""))
