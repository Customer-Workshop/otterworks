"""Reads previously generated export files back out of the export archive.

Exports are rendered to disk by the export worker under ``EXPORT_ARCHIVE_DIR``
(optionally in per-folder subdirectories) and served back to the caller by name.
Every read is confined to the archive root: a name that resolves outside it is
treated as not found.
"""

from __future__ import annotations

import os

import structlog

logger = structlog.get_logger()

DEFAULT_ARCHIVE_DIR = "/var/lib/otterworks/exports"


class ExportArchive:
    """Serves rendered export files from the archive directory."""

    def __init__(self, base_dir: str | None = None):
        self.base_dir = base_dir or os.environ.get(
            "EXPORT_ARCHIVE_DIR", DEFAULT_ARCHIVE_DIR
        )

    def _resolve(self, name: str) -> str:
        """Return the joined path, or raise ``FileNotFoundError`` if it escapes the root."""
        path = os.path.join(self.base_dir, name)
        root = os.path.realpath(self.base_dir)
        resolved = os.path.realpath(path)
        if resolved != root and not resolved.startswith(root + os.sep):
            logger.warning("export_read_rejected", name=name)
            raise FileNotFoundError(f"Export not found: {name}")
        return path

    def read_export(self, name: str) -> str:
        """Return the contents of the named export.

        ``name`` may include a subdirectory (``"reports/q3.md"``) but must stay
        inside the archive root. Raises ``FileNotFoundError`` when the export does
        not exist or resolves outside the archive.
        """
        path = self._resolve(name)
        logger.debug("export_read", name=name)
        with open(path, encoding="utf-8") as handle:
            return handle.read()
