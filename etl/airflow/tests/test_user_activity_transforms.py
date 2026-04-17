"""Tests for user activity report transform functions."""

import pytest

from dags.user_activity_report import _build_user_activity_report


class TestBuildUserActivityReport:
    """Tests for the _build_user_activity_report function."""

    def test_empty_data(self):
        report = _build_user_activity_report("2024-01-15", [], [])

        assert report["report_type"] == "user_activity"
        assert report["report_date"] == "2024-01-15"
        assert report["trends"]["total_events"] == 0
        assert report["trends"]["avg_daily_events"] == 0
        assert report["user_summaries"] == []

    def test_with_daily_summaries(self):
        daily_summaries = [
            {"report_date": "2024-01-14", "total_events": 100, "active_users": 10},
            {"report_date": "2024-01-15", "total_events": 150, "active_users": 15},
        ]
        report = _build_user_activity_report("2024-01-15", daily_summaries, [])

        assert report["trends"]["total_events"] == 250
        assert report["trends"]["peak_active_users"] == 15
        assert report["trends"]["avg_daily_events"] == 125.0
        assert report["trends"]["reporting_days"] == 2

    def test_with_user_activities(self):
        user_activities = [
            {"user_id": "u1", "total_actions": 50, "active_days": 5},
            {"user_id": "u2", "total_actions": 30, "active_days": 3},
            {"user_id": "u3", "total_actions": 10, "active_days": 1},
        ]
        report = _build_user_activity_report("2024-01-15", [], user_activities)

        assert len(report["user_summaries"]) == 3
        assert len(report["top_users"]) == 3
        assert report["top_users"][0]["user_id"] == "u1"

    def test_user_summaries_capped_at_500(self):
        user_activities = [
            {"user_id": f"u{i}", "total_actions": i}
            for i in range(600)
        ]
        report = _build_user_activity_report("2024-01-15", [], user_activities)

        assert len(report["user_summaries"]) == 500
        assert len(report["top_users"]) == 20

    def test_full_report(self):
        daily_summaries = [
            {
                "report_date": "2024-01-15",
                "total_events": 200,
                "active_users": 20,
                "documents_created": 5,
            },
        ]
        user_activities = [
            {
                "user_id": "u1",
                "total_actions": 50,
                "active_days": 10,
                "actions_by_type": {"document_created": 3, "document_edited": 47},
            },
        ]

        report = _build_user_activity_report("2024-01-15", daily_summaries, user_activities)

        assert report["report_type"] == "user_activity"
        assert report["lookback_days"] == 30
        assert report["trends"]["total_events"] == 200
        assert report["daily_summaries"] == daily_summaries
        assert report["user_summaries"][0]["user_id"] == "u1"
