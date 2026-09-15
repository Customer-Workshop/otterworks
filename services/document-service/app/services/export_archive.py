"""Reads previously generated export files back out of the export archive.

Exports are rendered to disk by the export worker under ``EXPORT_ARCHIVE_DIR``
(optionally in per-folder subdirectories) and served back to the caller by name.
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

    def resolve_export_path(self, name: str) -> str:
        """Return the absolute on-disk path for ``name``.

        ``name`` must be a relative path made of plain segments (no ``..``,
        no absolute prefix, no backslashes) and must resolve inside
        ``base_dir``. Anything else raises ``FileNotFoundError``.
        """
        segments = name.split("/")
        if (
            "\\" in name
            or "\x00" in name
            or os.path.isabs(name)
            or any(segment in ("", ".", "..") for segment in segments)
        ):
            raise FileNotFoundError(f"Invalid export name: {name!r}")

        root = os.path.realpath(self.base_dir)
        path = os.path.realpath(os.path.join(root, *segments))
        if os.path.commonpath([root, path]) != root:
            raise FileNotFoundError(f"Export outside archive: {name!r}")
        return path

    def read_export(self, name: str) -> str:
        """Return the contents of the named export.

        ``name`` may include a subdirectory (``"reports/q3.md"``). Raises
        ``FileNotFoundError`` when the export does not exist or the name
        escapes the archive directory.
        """
        path = self.resolve_export_path(name)
        logger.debug("export_read", name=name)
        with open(path, encoding="utf-8") as handle:
            return handle.read()
