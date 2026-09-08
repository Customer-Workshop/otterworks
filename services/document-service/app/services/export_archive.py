"""Reads previously generated export files back out of the export archive.

Exports are rendered to disk by the export worker under ``EXPORT_ARCHIVE_DIR``
(optionally in per-folder subdirectories) and served back to the caller by name.
A name is only ever opened when the path it resolves to stays inside the
archive root.
"""

from __future__ import annotations

import errno
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

    def _contained_path(self, name: str) -> str:
        """Return the archive path for ``name``, or raise if it escapes the root.

        Containment is decided on the fully resolved paths (symlinks and ``..``
        collapsed), so neither traversal segments nor an absolute ``name`` can
        reach outside the archive. Escapes surface as ``FileNotFoundError`` so a
        caller learns nothing about what exists beyond the root.
        """
        root = os.path.realpath(self.base_dir)
        path = os.path.join(self.base_dir, name)
        resolved = os.path.realpath(path)
        if os.path.commonpath([root, resolved]) != root:
            logger.warning("export_read_rejected", name=name)
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), name)
        return path

    def read_export(self, name: str) -> str:
        """Return the contents of the named export.

        ``name`` may include a subdirectory (``"reports/q3.md"``). Raises
        ``FileNotFoundError`` when the export does not exist or when ``name``
        resolves outside the archive.
        """
        path = self._contained_path(name)
        logger.debug("export_read", name=name)
        with open(path, encoding="utf-8") as handle:
            return handle.read()
