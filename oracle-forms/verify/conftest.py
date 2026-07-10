"""Shared fixtures for the billing contract-parity harness.

The tests are black-box: they exercise the running Spring Boot service over HTTP
against the OpenAPI contract in oracle-forms/contracts/openapi.yaml. The base URL
is taken from BASE_URL (default http://localhost:8092).
"""

import os
import time

import pytest
import requests

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8092")


@pytest.fixture(scope="session", autouse=True)
def wait_for_service():
    """Block until the service answers /health, so tests fail as assertions, not connection errors."""
    deadline = time.time() + 60
    last_err = None
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE_URL}/health", timeout=2)
            if r.status_code == 200:
                return
        except requests.RequestException as exc:  # noqa: PERF203
            last_err = exc
        time.sleep(1)
    pytest.fail(f"Service at {BASE_URL} never became healthy: {last_err}")


@pytest.fixture
def base_url():
    return BASE_URL


@pytest.fixture
def make_customer(base_url):
    """Factory that creates a customer and returns its id."""

    def _make(company="Acme Corp", email="ops@acme.example", status=None):
        body = {"companyName": company, "contactEmail": email}
        if status is not None:
            body["status"] = status
        r = requests.post(f"{base_url}/api/customers", json=body, timeout=5)
        assert r.status_code == 201, f"customer setup failed: {r.status_code} {r.text}"
        return r.json()["customerId"]

    return _make
