import asyncio
import json
from collections.abc import AsyncIterator, Mapping, MutableMapping
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from typing import Any, Self

from fastapi import FastAPI

type Message = MutableMapping[str, Any]

DEFAULT_TIMEOUT = 3.0


@asynccontextmanager
async def running(app: FastAPI) -> AsyncIterator[FastAPI]:
    async with app.router.lifespan_context(app):
        yield app


@dataclass(slots=True)
class Frame:
    comment: str | None = None
    event: str | None = None
    id: str | None = None
    retry: int | None = None
    data: list[str] = field(default_factory=list)

    @property
    def payload(self) -> dict[str, Any]:
        return dict(json.loads("\n".join(self.data)))

    @property
    def empty(self) -> bool:
        return self == Frame()

    def feed(self, line: str) -> None:
        if line.startswith(":"):
            self.comment = line[1:].strip()
        elif line.startswith("data:"):
            self.data.append(line[5:].strip())
        elif line.startswith("event:"):
            self.event = line[6:].strip()
        elif line.startswith("id:"):
            self.id = line[3:].strip()
        elif line.startswith("retry:"):
            self.retry = int(line[6:].strip())


class Stream:
    def __init__(self, app: FastAPI, path: str, headers: Mapping[str, str]) -> None:
        self._app = app
        self._path, _, self._query = path.partition("?")
        self._headers = dict(headers)
        self._messages: asyncio.Queue[Message] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._disconnect = asyncio.Event()
        self._requested = False
        self._buffer = ""
        self.status = 0
        self.headers: dict[str, str] = {}
        self.ended = False

    async def _receive(self) -> Message:
        if not self._requested:
            self._requested = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await self._disconnect.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message: Message) -> None:
        await self._messages.put(message)

    async def _run(self) -> None:
        scope: Message = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": self._path,
            "raw_path": self._path.encode(),
            "query_string": self._query.encode(),
            "root_path": "",
            "headers": [(k.lower().encode(), v.encode()) for k, v in self._headers.items()],
            "client": ("testclient", 50_000),
            "server": ("testserver", 80),
            "state": {},
        }
        await self._app(scope, self._receive, self._send)
        await self._messages.put({"type": "http.response.body", "body": b"", "more_body": False})

    async def open(self) -> Self:
        self._task = asyncio.create_task(self._run())
        start = await asyncio.wait_for(self._messages.get(), DEFAULT_TIMEOUT)
        assert start["type"] == "http.response.start", start
        self.status = start["status"]
        self.headers = {key.decode(): value.decode() for key, value in start["headers"]}
        return self

    async def close(self) -> None:
        self._disconnect.set()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def next_line(self, timeout: float = DEFAULT_TIMEOUT) -> str | None:
        while "\n" not in self._buffer:
            if self.ended:
                return None
            message = await asyncio.wait_for(self._messages.get(), timeout)
            if message.get("type") != "http.response.body":
                continue
            self._buffer += bytes(message.get("body", b"")).decode()
            if not message.get("more_body", False):
                self.ended = True
        line, separator, rest = self._buffer.partition("\n")
        if not separator:
            return None
        self._buffer = rest
        return line

    async def next_frame(self, timeout: float = DEFAULT_TIMEOUT) -> Frame | None:
        frame = Frame()
        while True:
            line = await self.next_line(timeout)
            if line is None:
                return None if frame.empty else frame
            if line == "":
                if not frame.empty:
                    return frame
                continue
            frame.feed(line)

    async def rest(self, timeout: float = DEFAULT_TIMEOUT) -> list[Frame]:
        collected: list[Frame] = []
        while True:
            frame = await self.next_frame(timeout)
            if frame is None:
                return collected
            collected.append(frame)


@asynccontextmanager
async def open_stream(app: FastAPI, path: str, headers: Mapping[str, str]) -> AsyncIterator[Stream]:
    stream = await Stream(app, path, headers).open()
    try:
        yield stream
    finally:
        await stream.close()


async def call(app: FastAPI, method: str, path: str, **kwargs: Any) -> tuple[int, Any]:
    import httpx  # noqa: PLC0415 - only the tests need a client

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.request(method, path, **kwargs)
    body = None
    if response.content:
        with suppress(json.JSONDecodeError):
            body = response.json()
    return response.status_code, body


async def login(app: FastAPI, email: str, password: str) -> dict[str, str]:
    status, body = await call(
        app, "POST", "/v1/auth/login", json={"email": email, "password": password}
    )
    assert status == 200, body
    assert isinstance(body, dict)
    return {"Authorization": f"Bearer {body['access_token']}"}
