"""Scripted WebSocket doubles."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


class FakeClosedError(Exception):
    """Raised from ``recv`` when the scripted socket closes."""


class FakeWebSocket:
    """A socket whose incoming frames are pushed by the test."""

    def __init__(self) -> None:
        self._incoming: asyncio.Queue[str | BaseException] = asyncio.Queue()
        self.sent: list[str] = []
        self.closed: bool = False

    def push(self, frame: object) -> None:
        """Queue a frame (serialised to JSON unless it is already a string)."""
        self._incoming.put_nowait(frame if isinstance(frame, str) else json.dumps(frame))

    def drop(self) -> None:
        """Simulate the server closing the connection."""
        self._incoming.put_nowait(FakeClosedError("server went away"))

    async def recv(self) -> str | bytes:
        item = await self._incoming.get()
        if isinstance(item, BaseException):
            raise item
        return item

    async def send(self, message: str) -> None:
        if self.closed:
            raise FakeClosedError("closed")
        self.sent.append(message)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = True
        self._incoming.put_nowait(FakeClosedError("closed by client"))

    def sent_json(self) -> list[object]:
        return [json.loads(m) for m in self.sent]


@dataclass
class FakeConnector:
    """Hands out sockets (or raises) per connection attempt and records handshakes."""

    outcomes: list[FakeWebSocket | BaseException] = field(default_factory=list)
    calls: list[tuple[str, Mapping[str, str]]] = field(default_factory=list)
    sockets: list[FakeWebSocket] = field(default_factory=list)

    async def __call__(self, url: str, headers: Mapping[str, str]) -> FakeWebSocket:
        self.calls.append((url, dict(headers)))
        outcome = self.outcomes.pop(0) if self.outcomes else FakeWebSocket()
        if isinstance(outcome, BaseException):
            raise outcome
        self.sockets.append(outcome)
        return outcome

    @property
    def current(self) -> FakeWebSocket:
        return self.sockets[-1]
