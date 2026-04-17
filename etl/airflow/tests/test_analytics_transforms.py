"""Tests for analytics ETL transform functions."""

import pytest

from dags.analytics_etl import (
    _aggregate_events,
    _build_daily_report,
    _find_peak_hour,
)


class TestAggregateEvents:
    """Tests for the _aggregate_events function."""

    def test_empty_events(self):
        result = _aggregate_events([], "2024-01-15")
        assert result["date"] == "2024-01-15"
        assert result["summary"]["active_users"] == 0
        assert result["summary"]["total_events"] == 0
        assert result["top_users"] == []

    def test_single_document_created_event(self):
        events = [
            {
                "eventType": "document_created",
                "documentId": "doc-1",
                "ownerId": "user-1",
                "title": "Test Doc",
                "timestamp": "2024-01-15T10:00:00Z",
            }
        ]
        result = _aggregate_events(events, "2024-01-15")

        assert result["summary"]["active_users"] == 1
        assert result["summary"]["documents_created"] == 1
        assert result["summary"]["total_events"] == 1
        assert result["summary"]["active_documents"] == 1

    def test_multiple_event_types(self):
        events = [
            {
                "eventType": "document_created",
                "documentId": "doc-1",
                "ownerId": "user-1",
                "timestamp": "2024-01-15T10:00:00Z",
            },
            {
                "eventType": "document_edited",
                "documentId": "doc-1",
                "editedBy": "user-2",
                "timestamp": "2024-01-15T11:00:00Z",
            },
            {
                "eventType": "file_uploaded",
                "fileId": "file-1",
                "ownerId": "user-1",
                "sizeBytes": 1024,
                "timestamp": "2024-01-15T12:00:00Z",
            },
            {
                "eventType": "comment_added",
                "documentId": "doc-1",
                "authorId": "user-3",
                "timestamp": "2024-01-15T13:00:00Z",
            },
            {
                "eventType": "file_shared",
                "fileId": "file-1",
                "ownerId": "user-1",
                "timestamp": "2024-01-15T14:00:00Z",
            },
            {
                "eventType": "file_deleted",
                "fileId": "file-2",
                "deletedBy": "user-2",
                "timestamp": "2024-01-15T15:00:00Z",
            },
        ]
        result = _aggregate_events(events, "2024-01-15")

        assert result["summary"]["active_users"] == 3
        assert result["summary"]["documents_created"] == 1
        assert result["summary"]["documents_edited"] == 1
        assert result["summary"]["comments_added"] == 1
        assert result["summary"]["files_uploaded"] == 1
        assert result["summary"]["files_shared"] == 1
        assert result["summary"]["files_deleted"] == 1
        assert result["summary"]["bytes_uploaded"] == 1024
        assert result["summary"]["total_events"] == 6
        assert result["summary"]["active_documents"] == 1
        assert result["summary"]["active_files"] == 2

    def test_hourly_breakdown(self):
        events = [
            {
                "eventType": "document_created",
                "ownerId": "user-1",
                "documentId": "doc-1",
                "timestamp": "2024-01-15T10:30:00Z",
            },
            {
                "eventType": "document_edited",
                "editedBy": "user-1",
                "documentId": "doc-1",
                "timestamp": "2024-01-15T10:45:00Z",
            },
            {
                "eventType": "file_uploaded",
                "ownerId": "user-2",
                "fileId": "file-1",
                "sizeBytes": 512,
                "timestamp": "2024-01-15T14:00:00Z",
            },
        ]
        result = _aggregate_events(events, "2024-01-15")

        assert "10" in result["hourly_breakdown"]
        assert "14" in result["hourly_breakdown"]
        assert result["hourly_breakdown"]["10"]["document_created"] == 1
        assert result["hourly_breakdown"]["10"]["document_edited"] == 1
        assert result["hourly_breakdown"]["14"]["file_uploaded"] == 1

    def test_top_users_sorted_by_activity(self):
        events = []
        # user-1: 5 events, user-2: 2 events, user-3: 1 event
        for i in range(5):
            events.append(
                {
                    "eventType": "document_edited",
                    "editedBy": "user-1",
                    "documentId": f"doc-{i}",
                    "timestamp": f"2024-01-15T{10+i}:00:00Z",
                }
            )
        for i in range(2):
            events.append(
                {
                    "eventType": "file_uploaded",
                    "ownerId": "user-2",
                    "fileId": f"file-{i}",
                    "sizeBytes": 100,
                    "timestamp": f"2024-01-15T{10+i}:00:00Z",
                }
            )
        events.append(
            {
                "eventType": "comment_added",
                "authorId": "user-3",
                "documentId": "doc-0",
                "timestamp": "2024-01-15T10:00:00Z",
            }
        )

        result = _aggregate_events(events, "2024-01-15")

        assert len(result["top_users"]) == 3
        assert result["top_users"][0]["user_id"] == "user-1"
        assert result["top_users"][0]["total"] == 5
        assert result["top_users"][1]["user_id"] == "user-2"
        assert result["top_users"][1]["total"] == 2

    def test_user_resolution_fallback(self):
        events = [
            {
                "eventType": "document_created",
                "timestamp": "2024-01-15T10:00:00Z",
            },
        ]
        result = _aggregate_events(events, "2024-01-15")

        assert result["summary"]["active_users"] == 1
        assert result["top_users"][0]["user_id"] == "unknown"

    def test_malformed_timestamp(self):
        events = [
            {
                "eventType": "document_created",
                "ownerId": "user-1",
                "documentId": "doc-1",
                "timestamp": "not-a-timestamp",
            },
        ]
        result = _aggregate_events(events, "2024-01-15")

        # Should still process the event, just default to hour "00"
        assert result["summary"]["total_events"] == 1
        assert "00" in result["hourly_breakdown"]


class TestFindPeakHour:
    """Tests for the _find_peak_hour function."""

    def test_empty_breakdown(self):
        assert _find_peak_hour({}) is None

    def test_single_hour(self):
        breakdown = {"10": {"document_created": 5, "file_uploaded": 3}}
        result = _find_peak_hour(breakdown)
        assert result["hour"] == "10"
        assert result["event_count"] == 8

    def test_multiple_hours(self):
        breakdown = {
            "09": {"document_created": 2},
            "10": {"document_created": 5, "file_uploaded": 3},
            "14": {"document_edited": 1},
        }
        result = _find_peak_hour(breakdown)
        assert result["hour"] == "10"
        assert result["event_count"] == 8


class TestBuildDailyReport:
    """Tests for the _build_daily_report function."""

    def test_basic_report_structure(self):
        summary = {"active_users": 10, "total_events": 100}
        aggregated = {
            "summary": summary,
            "hourly_breakdown": {"10": {"document_created": 50}},
            "top_users": [
                {"user_id": "u1", "total": 20},
                {"user_id": "u2", "total": 15},
            ],
            "document_metrics": {"created": 5},
            "file_metrics": {"uploaded": 3},
        }

        report = _build_daily_report("2024-01-15", summary, aggregated)

        assert report["report_type"] == "daily_analytics"
        assert report["report_date"] == "2024-01-15"
        assert report["summary"]["active_users"] == 10
        assert len(report["highlights"]["most_active_users"]) == 2
        assert report["highlights"]["peak_hour"]["hour"] == "10"

    def test_report_with_no_data(self):
        summary = {}
        aggregated = {
            "summary": summary,
            "hourly_breakdown": {},
            "top_users": [],
            "document_metrics": {},
            "file_metrics": {},
        }

        report = _build_daily_report("2024-01-15", summary, aggregated)

        assert report["highlights"]["peak_hour"] is None
        assert report["highlights"]["most_active_users"] == []
