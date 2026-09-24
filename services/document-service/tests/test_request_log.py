"""The per-request debug log never retains request credentials."""

import json
import uuid

import pytest
from httpx import AsyncClient

from app.chaos import FLAG_REQUEST_LOG
from app.middleware import request_log as request_log_module
from app.middleware.request_log import REDACTED, RequestLog, redact_headers


def test_redact_headers_masks_credentials_only() -> None:
    redacted = redact_headers(
        {
            "Authorization": "Bearer secret",
            "Cookie": "session=abc",
            "Proxy-Authorization": "Basic xyz",
            "X-API-Key": "k",
            "Accept": "application/json",
        }
    )
    assert redacted["Authorization"] == REDACTED
    assert redacted["Cookie"] == REDACTED
    assert redacted["Proxy-Authorization"] == REDACTED
    assert redacted["X-API-Key"] == REDACTED
    assert redacted["Accept"] == "application/json"


@pytest.mark.asyncio
async def test_logged_request_keeps_body_but_not_bearer_token(
    client: AsyncClient,
    owner_id: uuid.UUID,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(request_log_module, "flag_active", lambda key: key == FLAG_REQUEST_LOG)
    monkeypatch.setattr(request_log_module, "request_log", RequestLog(str(tmp_path)))

    resp = await client.get(
        "/api/v1/documents/",
        params={"owner_id": str(owner_id)},
        headers={"Authorization": "Bearer top-secret", "Cookie": "sid=1"},
    )
    assert resp.status_code == 200

    files = list(tmp_path.iterdir())
    assert len(files) == 1
    raw = files[0].read_text()
    assert "top-secret" not in raw
    assert "sid=1" not in raw
    record = json.loads(raw.splitlines()[-1])
    assert record["headers"]["authorization"] == REDACTED
    assert record["headers"]["cookie"] == REDACTED
    assert json.loads(record["response"])["total"] == 0
