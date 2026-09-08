"""Parity tests: storage cleanup transforms vs ``etl/scripts/storage_cleanup_daily.py``."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from otterworks.storage_cleanup_transforms import (
    FILES_PREFIX,
    QUARANTINE_PREFIX,
    build_storage_report,
    extract_referenced_keys,
    find_orphaned_objects,
    normalize_s3_object,
    quarantine_key,
    storage_report_key,
    summarize_inventory,
)


def _legacy_format(source: str, pattern: str) -> str:
    match = re.search(pattern, source)
    assert match, f"legacy pattern not found: {pattern}"
    return match.group(1)


class TestS3KeyFormats:
    def test_quarantine_key_matches_legacy_template(self, legacy_storage_cleanup_source):
        template = _legacy_format(legacy_storage_cleanup_source, r'dest_key = "([^"]+)" %')
        assert template == "%s/%s/%s"
        legacy = template % (QUARANTINE_PREFIX, "2024-03-07", "files/u1/doc.pdf")
        assert quarantine_key("2024-03-07", "files/u1/doc.pdf") == legacy
        assert legacy == "quarantined/2024-03-07/files/u1/doc.pdf"

    def test_quarantine_prefix_and_files_prefix_match_legacy(self, legacy_storage_cleanup_source):
        assert (
            _legacy_format(legacy_storage_cleanup_source, r'quarantine_prefix = "([^"]+)"')
            == QUARANTINE_PREFIX
        )
        assert (
            _legacy_format(legacy_storage_cleanup_source, r'files_prefix = "([^"]+)"')
            == FILES_PREFIX
        )

    def test_report_key_matches_legacy_template(self, legacy_storage_cleanup_source):
        template = _legacy_format(legacy_storage_cleanup_source, r'report_key = "([^"]+)" % ds')
        assert storage_report_key("2024-03-07") == template % "2024-03-07"
        assert storage_report_key("2024-03-07") == "reports/storage-cleanup/2024-03-07/report.json"


class TestInventoryAndOrphans:
    def test_normalize_s3_object_matches_legacy_record_shape(self):
        ts = datetime(2024, 3, 6, 12, 30, tzinfo=UTC)
        record = normalize_s3_object({"Key": "files/a", "Size": 10, "LastModified": ts})
        assert record == {"key": "files/a", "size": 10, "last_modified": ts.isoformat()}

    def test_summarize_inventory(self):
        objects = [
            {"key": "files/a", "size": 10, "last_modified": "x"},
            {"key": "files/b", "size": 32, "last_modified": "y"},
        ]
        assert summarize_inventory(objects) == (2, 42)
        assert summarize_inventory([]) == (0, 0)

    def test_extract_referenced_keys_skips_missing_and_empty(self):
        items = [{"s3_key": "files/a"}, {"s3_key": ""}, {"other": 1}, {"s3_key": "files/b"}]
        assert extract_referenced_keys(items) == {"files/a", "files/b"}

    def test_find_orphaned_objects_preserves_order_and_bytes(self):
        objects = [
            {"key": "files/a", "size": 1, "last_modified": ""},
            {"key": "files/b", "size": 20, "last_modified": ""},
            {"key": "files/c", "size": 300, "last_modified": ""},
        ]
        orphaned, orphaned_bytes = find_orphaned_objects(objects, {"files/b"})
        assert [o["key"] for o in orphaned] == ["files/a", "files/c"]
        assert orphaned_bytes == 301


class TestStorageReport:
    @pytest.mark.parametrize(
        ("total_objects", "total_size_bytes", "orphaned_count", "orphaned_bytes"),
        [
            (1000, 5 * 1024**3, 37, 1_500_000_000),
            (0, 0, 0, 0),
            (3, 1024**3 + 7, 3, 1024**3 + 7),
        ],
    )
    def test_report_matches_legacy_math(
        self, total_objects, total_size_bytes, orphaned_count, orphaned_bytes, report_date
    ):
        generated_at = "2024-03-07T02:31:00+00:00"
        report = build_storage_report(
            report_date=report_date,
            generated_at=generated_at,
            total_objects=total_objects,
            total_size_bytes=total_size_bytes,
            orphaned_count=orphaned_count,
            orphaned_bytes=orphaned_bytes,
            moved_count=orphaned_count - 1 if orphaned_count else 0,
            failed_count=1 if orphaned_count else 0,
            quarantine_bucket="otterworks-file-quarantine",
        )

        # Legacy computation, copied verbatim from storage_cleanup_daily.py
        savings_gb = orphaned_bytes / (1024**3)
        estimated_monthly_savings = round(savings_gb * 0.023, 4)
        expected = {
            "report_type": "storage_cleanup",
            "report_date": report_date,
            "generated_at": generated_at,
            "inventory": {
                "total_objects": total_objects,
                "total_size_bytes": total_size_bytes,
                "total_size_gb": round(total_size_bytes / (1024**3), 4),
            },
            "orphans": {
                "orphaned_objects": orphaned_count,
                "orphaned_bytes": orphaned_bytes,
                "orphaned_size_gb": round(savings_gb, 4),
                "orphan_percentage": round(
                    (orphaned_count / total_objects * 100) if total_objects else 0, 2
                ),
            },
            "cleanup": {
                "objects_quarantined": orphaned_count - 1 if orphaned_count else 0,
                "objects_failed": 1 if orphaned_count else 0,
                "quarantine_bucket": "otterworks-file-quarantine",
            },
            "savings": {
                "storage_freed_gb": round(savings_gb, 4),
                "estimated_monthly_savings_usd": estimated_monthly_savings,
            },
        }
        assert report == expected
        assert list(report) == list(expected)  # same JSON key order

    def test_report_uses_legacy_s3_price(self, legacy_storage_cleanup_source):
        assert "savings_gb * 0.023" in legacy_storage_cleanup_source
        report = build_storage_report(
            report_date="2024-03-07",
            generated_at="x",
            total_objects=1,
            total_size_bytes=1024**3,
            orphaned_count=1,
            orphaned_bytes=1024**3,
            moved_count=1,
            failed_count=0,
            quarantine_bucket="q",
        )
        assert report["savings"]["estimated_monthly_savings_usd"] == 0.023
        assert report["orphans"]["orphan_percentage"] == 100.0
