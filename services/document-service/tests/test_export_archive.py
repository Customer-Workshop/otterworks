"""Tests for the export archive reader."""

import pytest

from app.services import export_archive
from app.services.export_archive import ExportArchive


@pytest.fixture
def archive(tmp_path):
    (tmp_path / "report.md").write_text("# Report\n", encoding="utf-8")
    nested = tmp_path / "reports"
    nested.mkdir()
    (nested / "q3.md").write_text("# Q3\n", encoding="utf-8")
    return ExportArchive(base_dir=str(tmp_path))


def test_reads_export(archive):
    assert archive.read_export("report.md") == "# Report\n"


def test_reads_export_in_subdirectory(archive):
    assert archive.read_export("reports/q3.md") == "# Q3\n"


def test_missing_export_raises(archive):
    with pytest.raises(FileNotFoundError):
        archive.read_export("absent.md")


@pytest.fixture
def secret_outside_archive(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("top secret\n", encoding="utf-8")
    return secret


@pytest.mark.parametrize(
    "name",
    [
        "../{secret}",
        "reports/../../{secret}",
        "./report.md",
        "reports//q3.md",
        "reports\\q3.md",
        "report.md\x00",
    ],
)
def test_rejects_traversal_and_malformed_names(archive, secret_outside_archive, name):
    name = name.format(secret=f"{secret_outside_archive.parent.name}/secret.txt")
    with pytest.raises(FileNotFoundError):
        archive.read_export(name)


def test_rejects_absolute_path(archive, secret_outside_archive):
    with pytest.raises(FileNotFoundError):
        archive.read_export(str(secret_outside_archive))
    with pytest.raises(FileNotFoundError):
        archive.read_export("/etc/passwd")


def test_rejects_symlink_escaping_archive(tmp_path, archive, secret_outside_archive):
    (tmp_path / "link.md").symlink_to(secret_outside_archive)
    with pytest.raises(FileNotFoundError):
        archive.read_export("link.md")


def test_rejects_symlink_swapped_in_after_resolution(
    tmp_path, archive, secret_outside_archive, monkeypatch
):
    real_resolve = archive.resolve_export_path

    def resolve_then_swap(name):
        path = real_resolve(name)
        (tmp_path / "report.md").unlink()
        (tmp_path / "report.md").symlink_to(secret_outside_archive)
        return path

    monkeypatch.setattr(archive, "resolve_export_path", resolve_then_swap)
    with pytest.raises(OSError):
        archive.read_export("report.md")


def test_rejects_parent_directory_swapped_for_symlink_after_resolution(
    tmp_path, archive, secret_outside_archive, monkeypatch
):
    (secret_outside_archive.parent / "q3.md").write_text("leaked\n", encoding="utf-8")
    real_resolve = archive.resolve_export_path

    def resolve_then_swap_parent(name):
        path = real_resolve(name)
        (tmp_path / "reports" / "q3.md").unlink()
        (tmp_path / "reports").rmdir()
        (tmp_path / "reports").symlink_to(secret_outside_archive.parent)
        return path

    monkeypatch.setattr(archive, "resolve_export_path", resolve_then_swap_parent)
    with pytest.raises(OSError):
        archive.read_export("reports/q3.md")


def test_rejects_directory(archive):
    with pytest.raises(OSError):
        archive.read_export("reports")


@pytest.mark.asyncio
async def test_export_endpoint_serves_archived_file(client, monkeypatch, tmp_path):
    (tmp_path / "report.md").write_text("# Report\n", encoding="utf-8")
    monkeypatch.setenv("EXPORT_ARCHIVE_DIR", str(tmp_path))

    resp = await client.get("/api/v1/documents/exports", params={"name": "report.md"})

    assert resp.status_code == 200
    assert resp.text == "# Report\n"


@pytest.mark.asyncio
async def test_export_endpoint_404s_for_path_traversal(
    client, monkeypatch, tmp_path, secret_outside_archive
):
    monkeypatch.setenv("EXPORT_ARCHIVE_DIR", str(tmp_path))
    traversal = f"../{secret_outside_archive.parent.name}/secret.txt"

    for name in (traversal, "../../../../etc/passwd", "/etc/passwd"):
        resp = await client.get("/api/v1/documents/exports", params={"name": name})
        assert resp.status_code == 404, name
        assert "top secret" not in resp.text
        assert "root:" not in resp.text


@pytest.mark.asyncio
async def test_export_endpoint_404s_for_unknown_name(client, monkeypatch, tmp_path):
    monkeypatch.setenv("EXPORT_ARCHIVE_DIR", str(tmp_path))

    resp = await client.get("/api/v1/documents/exports", params={"name": "absent.md"})

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_endpoint_404s_for_undecodable_file(client, monkeypatch, tmp_path):
    (tmp_path / "report.bin").write_bytes(b"\xff\xfe\x00binary")
    monkeypatch.setenv("EXPORT_ARCHIVE_DIR", str(tmp_path))

    resp = await client.get("/api/v1/documents/exports", params={"name": "report.bin"})

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_endpoint_404s_for_unreadable_file(client, monkeypatch, tmp_path):
    (tmp_path / "locked.md").write_text("# Locked\n", encoding="utf-8")
    monkeypatch.setenv("EXPORT_ARCHIVE_DIR", str(tmp_path))

    def refuse(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(export_archive, "open", refuse, raising=False)

    resp = await client.get("/api/v1/documents/exports", params={"name": "locked.md"})

    assert resp.status_code == 404
