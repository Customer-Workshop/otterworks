"""Per-request debug log.

When the ``request_log`` flag is on, every API request is appended to a JSONL
file under ``settings.request_log_dir`` together with the full response body,
so support can replay what a customer actually received.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import socket
import time
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI, Request, Response
from starlette.responses import StreamingResponse

from app.chaos import FLAG_REQUEST_LOG, flag_active
from app.config import settings
from app.telemetry import REQUEST_LOG_BYTES, REQUEST_LOG_CAPACITY_BYTES, SERVICE

logger = structlog.get_logger()

SKIP_PATHS = ("/health", "/metrics", "/ready")


class RequestLog:
    def __init__(self, directory: str) -> None:
        self.directory = directory
        self.path = os.path.join(directory, f"requests-{socket.gethostname()}.jsonl")
        self._bytes = self._scan()

    def _scan(self) -> int:
        try:
            with os.scandir(self.directory) as it:
                total = sum(e.stat().st_size for e in it if e.is_file())
        except OSError:
            total = 0
        self._publish(total)
        return total

    def _publish(self, total: int) -> None:
        REQUEST_LOG_BYTES.labels(SERVICE).set(total)
        with contextlib.suppress(OSError):
            REQUEST_LOG_CAPACITY_BYTES.labels(SERVICE).set(shutil.disk_usage(self.directory).total)

    def append(self, record: dict) -> None:
        os.makedirs(self.directory, exist_ok=True)
        line = json.dumps(record, default=str) + "\n"
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line)
        self._bytes += len(line)
        self._publish(self._bytes)

    def purge(self) -> None:
        try:
            with os.scandir(self.directory) as it:
                for entry in it:
                    if entry.is_file():
                        os.unlink(entry.path)
        except OSError:
            pass
        self._bytes = self._scan()


request_log = RequestLog(settings.request_log_dir)


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def _request_log(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in SKIP_PATHS or not flag_active(FLAG_REQUEST_LOG):
            return await call_next(request)

        started = time.perf_counter()
        response = await call_next(request)
        body = b""
        if isinstance(response, StreamingResponse):
            async for chunk in response.body_iterator:
                body += chunk if isinstance(chunk, bytes) else chunk.encode()
        else:
            body = response.body

        request_log.append(
            {
                "ts": time.time(),
                "method": request.method,
                "path": request.url.path,
                "query": str(request.url.query),
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "headers": dict(request.headers),
                "response": body.decode("utf-8", errors="replace"),
            }
        )
        return Response(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
