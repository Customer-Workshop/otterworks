"""Unit tests for tp_dbx.client token/host resolution (no network)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import client  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("DATABRICKS_DEMO_TOKEN", "DATABRICKS_TOKEN", "DATABRICKS_DEMO_HOST",
                "DATABRICKS_HOST"):
        monkeypatch.delenv(var, raising=False)


def test_env_token_wins_without_calling_the_cli(monkeypatch):
    monkeypatch.setenv("DATABRICKS_DEMO_TOKEN", "demo-tok")
    monkeypatch.setattr(client.shutil, "which",
                        lambda name: pytest.fail("CLI must not be consulted"))
    assert client.resolve_token("https://x.cloud.databricks.com") == "demo-tok"
    monkeypatch.delenv("DATABRICKS_DEMO_TOKEN")
    monkeypatch.setenv("DATABRICKS_TOKEN", "std-tok")
    assert client.resolve_token("https://x.cloud.databricks.com") == "std-tok"


def test_cli_mints_a_token_when_no_env_token(monkeypatch):
    calls = []
    monkeypatch.setattr(client.shutil, "which", lambda name: "/usr/bin/databricks")

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"access_token": "minted"}), "")

    monkeypatch.setattr(client.subprocess, "run", fake_run)
    assert client.resolve_token("https://h.cloud.databricks.com") == "minted"
    assert calls[0][:2] == ["/usr/bin/databricks", "auth"]
    assert "--host" in calls[0] and "https://h.cloud.databricks.com" in calls[0]


def test_nothing_available_exits_with_a_clear_message(monkeypatch):
    monkeypatch.setattr(client.shutil, "which", lambda name: None)
    monkeypatch.delenv("DATABRICKS_CLIENT_ID", raising=False)
    monkeypatch.delenv("DATABRICKS_CLIENT_SECRET", raising=False)
    with pytest.raises(SystemExit, match="DATABRICKS_DEMO_TOKEN"):
        client.resolve_token("https://h.cloud.databricks.com")
    monkeypatch.setattr(client.shutil, "which", lambda name: "/usr/bin/databricks")

    def boom(cmd, **kw):
        raise subprocess.CalledProcessError(1, cmd, stderr="no SP configured")

    monkeypatch.setattr(client.subprocess, "run", boom)
    with pytest.raises(SystemExit, match="oauth-m2m"):
        client.resolve_token("https://h.cloud.databricks.com")


def test_oidc_mint_when_the_cli_cannot(monkeypatch):
    import io

    monkeypatch.setenv("DATABRICKS_CLIENT_ID", "sp-id")
    monkeypatch.setenv("DATABRICKS_CLIENT_SECRET", "sp-secret")
    monkeypatch.setattr(client.shutil, "which", lambda name: None)
    seen = {}

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        seen["auth"] = req.headers["Authorization"]
        seen["body"] = req.data
        return _Resp(json.dumps({"access_token": "oidc-minted"}).encode())

    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)
    assert client.resolve_token("https://h.cloud.databricks.com") == "oidc-minted"
    assert b"grant_type=client_credentials" in seen["body"]
    assert seen["auth"].startswith("Basic ")


def test_resolve_host_prefers_demo_host(monkeypatch):
    assert client.resolve_host() is None
    monkeypatch.setenv("DATABRICKS_HOST", "https://std")
    assert client.resolve_host() == "https://std"
    monkeypatch.setenv("DATABRICKS_DEMO_HOST", "https://demo")
    assert client.resolve_host() == "https://demo"
