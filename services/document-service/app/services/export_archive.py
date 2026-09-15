"""Reads previously generated export files back out of the export archive.

Exports are rendered to disk by the export worker under ``EXPORT_ARCHIVE_DIR``
(optionally in per-folder subdirectories) and served back to the caller by name.
"""

from __future__ import annotations

import os
import stat

import structlog

logger = structlog.get_logger()

DEFAULT_ARCHIVE_DIR = "/var/lib/otterworks/exports"

_OPEN_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC


class ExportArchive:
    """Serves rendered export files from the archive directory."""

    def __init__(self, base_dir: str | None = None):
        self.base_dir = base_dir or os.environ.get(
            "EXPORT_ARCHIVE_DIR", DEFAULT_ARCHIVE_DIR
        )

    @staticmethod
    def _split_name(name: str) -> list[str]:
        """Split ``name`` into path segments, rejecting anything that is not a
        relative path of plain segments (no ``..``, ``.``, empty segments,
        absolute prefix, backslashes or NUL bytes)."""
        segments = name.split("/")
        if (
            "\\" in name
            or "\x00" in name
            or os.path.isabs(name)
            or any(segment in ("", ".", "..") for segment in segments)
        ):
            raise FileNotFoundError(f"Invalid export name: {name!r}")
        return segments

    def resolve_export_path(self, name: str) -> str:
        """Return the absolute on-disk path for ``name``.

        ``name`` must be a relative path made of plain segments (no ``..``,
        no absolute prefix, no backslashes) and must resolve inside
        ``base_dir``. Anything else raises ``FileNotFoundError``.
        """
        segments = self._split_name(name)
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
        fd = self._open_export(name, path)
        try:
            with open(fd, encoding="utf-8") as handle:
                fd = -1
                return handle.read()
        finally:
            if fd != -1:
                os.close(fd)

    def _open_export(self, name: str, path: str) -> int:
        """Open ``name`` relative to ``base_dir`` one segment at a time with
        ``O_NOFOLLOW`` so no component, including parent directories, can be
        a symlink. Returns a file descriptor to a regular file. ``path`` is
        the resolved location, reported in any ``OSError`` raised."""
        *dirs, leaf = self._split_name(name)
        fd = os.open(os.path.realpath(self.base_dir), _OPEN_FLAGS | os.O_DIRECTORY)
        try:
            for segment in dirs:
                next_fd = os.open(segment, _OPEN_FLAGS | os.O_DIRECTORY, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            leaf_fd = os.open(leaf, _OPEN_FLAGS, dir_fd=fd)
        except OSError as exc:
            raise OSError(exc.errno, exc.strerror, path) from None
        finally:
            os.close(fd)
        if not stat.S_ISREG(os.fstat(leaf_fd).st_mode):
            os.close(leaf_fd)
            raise FileNotFoundError(f"Export is not a regular file: {name!r}")
        return leaf_fd
