"""Participant client for EPIC contests."""

from __future__ import annotations

import asyncio
import csv
import json
import time
from pathlib import Path
from typing import AsyncIterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen


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

    def list_contests(self, status: str | None = None) -> list[dict]:
        query = f"?{urlencode({'status': status})}" if status is not None else ""
        response = self._request("GET", f"/api/v1/contests{query}")
        contests = response["contests"]
        for contest in contests:
            if "contest_id" not in contest and "id" in contest:
                contest["contest_id"] = contest["id"]
        return contests

    async def stream(self, contest_id: str) -> AsyncIterator[dict]:
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
                        yield {
                            "sequence_id": payload["sequence_id"],
                            "timestamp": payload["timestamp"],
                            "sensors": payload["sensors"],
                        }
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
        writer = None
        csv_file = None

        if csv_path is not None:
            csv_file = Path(csv_path).open("w", newline="")
            writer = csv.DictWriter(
                csv_file,
                fieldnames=["sequence_id", "timestamp", "sensors"],
            )
            writer.writeheader()

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
                observations.append(observation)
                if writer is not None:
                    writer.writerow(
                        {
                            "sequence_id": observation["sequence_id"],
                            "timestamp": observation["timestamp"],
                            "sensors": json.dumps(observation["sensors"]),
                        }
                    )
        finally:
            if csv_file is not None:
                csv_file.close()

        return observations

    def submit(
        self,
        contest_id: str,
        task_id: str,
        prediction_from_sequence: int,
        payload: dict,
    ) -> dict:
        return self._request(
            "POST",
            f"/api/v1/contests/{contest_id}/submissions",
            {
                "task_id": task_id,
                "prediction_from_sequence": prediction_from_sequence,
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
            message = exc.read().decode("utf-8")
            raise RuntimeError(f"EPIC API request failed: {exc.code} {message}") from exc
        except URLError as exc:
            raise RuntimeError(f"EPIC API request failed: {exc.reason}") from exc

        if not response_body:
            return {}
        return json.loads(response_body.decode("utf-8"))

    def _require_token(self) -> None:
        if self._token is None:
            raise RuntimeError("Not authenticated. Call login() first.")

    def _websocket_url(self, path: str) -> str:
        self._require_token()
        parsed = urlparse(urljoin(self.server_url, path.lstrip("/")))
        scheme = "wss" if parsed.scheme == "https" else "ws"
        query = urlencode({"token": self._token})
        return urlunparse((scheme, parsed.netloc, parsed.path, "", query, ""))
