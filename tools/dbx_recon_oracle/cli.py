"""Runtime registration wrapper for the Oracle dbx-recon adapter."""

from __future__ import annotations

import recon
import recon.adapters
import recon.cli

from .adapter import OracleSourceAdapter


def main(argv: list[str] | None = None) -> int:
    recon.adapters.SOURCE_ADAPTERS["oracle"] = OracleSourceAdapter
    return recon.cli.main(argv)
