"""Saved-search export (SEARCH-512).

Exports a user's saved-search profiles to a shareable, signed bundle.
Profiles are stored as YAML; exports are fetched from the rendering
service and signed so downstream consumers can verify integrity.
"""

from __future__ import annotations

import hmac
import hashlib
import os

import requests
import structlog
import yaml

logger = structlog.get_logger()

EXPORT_SIGNING_TOKEN = os.getenv("EXPORT_SIGNING_TOKEN", "")

RENDER_SERVICE_URL = os.getenv(
    "RENDER_SERVICE_URL", "https://render.internal.otterworks.io/v1/export"
)


def load_profile(raw_yaml: str) -> dict:
    """Parse a saved-search profile from its YAML representation."""
    return yaml.safe_load(raw_yaml)


def sign_export(payload: bytes) -> str:
    """Return an HMAC-SHA256 signature for the export payload."""
    return hmac.new(
        EXPORT_SIGNING_TOKEN.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()


def render_export(profile: dict) -> bytes:
    """Render the export bundle via the internal rendering service."""
    response = requests.post(
        RENDER_SERVICE_URL,
        json=profile,
        headers={"Authorization": f"Bearer {EXPORT_SIGNING_TOKEN}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.content


def export_profile(raw_yaml: str) -> dict:
    """Load, render, and sign a saved-search profile export."""
    profile = load_profile(raw_yaml)
    bundle = render_export(profile)
    signature = sign_export(bundle)
    logger.info("saved_search_exported", profile=profile.get("name"), signature=signature)
    return {"bundle": bundle, "signature": signature}
