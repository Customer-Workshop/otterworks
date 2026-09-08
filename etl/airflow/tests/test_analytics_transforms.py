"""Parity tests: analytics transforms vs ``etl/scripts/analytics_daily.py``.

The aggregation oracle is ``tests/legacy_reference.py``, a verbatim copy of the
legacy pandas block, so every assertion here is "same input -> same JSON".
"""

from __future__ import annotations

import gzip
import json
import random
import re
from decimal import Decimal

import pytest

from legacy_reference import legacy_aggregate
from otterworks.analytics_transforms import (
    ANALYTICS_UPSERT_SQL,
    SUMMARY_COLUMNS,
    aggregate_events,
    analytics_report_key,
    build_analytics_report,
    encode_gzip_json,
    encode_gzip_jsonl,
    encode_json,
    find_peak_hour,
    hourly_breakdown_key,
    normalize_dynamodb_item,
    parse_hour,
    partition_key,
    resolve_event_type,
    resolve_user_id,
    summary_key,
    summary_upsert_params,
    top_users_key,
)

PREFIX = "analytics/daily"

EVENT_TYPES = [
    "document_created",
    "document_edited",
    "comment_added",
    "file_uploaded",
    "file_shared",
    "file_deleted",
    "login",
]
USER_FIELDS = ["ownerId", "editedBy", "authorId", "deletedBy", "userId"]


def _sample_events() -> list[dict]:
    return [
        {
            "eventType": "document_created",
            "ownerId": "u1",
            "documentId": "d1",
            "timestamp": "2024-03-07T09:15:00Z",
        },
        {
            "eventType": "document_edited",
            "editedBy": "u2",
            "documentId": "d1",
            "timestamp": "2024-03-07T09:45:00+00:00",
        },
        {
            "eventType": "document_edited",
            "editedBy": "u2",
            "documentId": "d2",
            "timestamp": "2024-03-07T14:00:00Z",
        },
        {
            "eventType": "comment_added",
            "authorId": "u3",
            "documentId": "d1",
            "timestamp": "2024-03-07T14:05:00Z",
        },
        {
            "eventType": "file_uploaded",
            "userId": "u1",
            "fileId": "f1",
            "sizeBytes": 1024,
            "timestamp": "2024-03-07T23:59:59Z",
        },
        {
            "eventType": "file_uploaded",
            "userId": "u4",
            "fileId": "f2",
            "sizeBytes": 2048,
            "timestamp": "2024-03-07T23:00:00-05:00",  # hour is taken in its own offset
        },
        {"eventType": "file_shared", "userId": "u1", "fileId": "f1", "timestamp": "not-a-date"},
        {"eventType": "file_deleted", "deletedBy": "u4", "fileId": "f2"},
        {"eventType": "login", "userId": "", "timestamp": "2024-03-07T09:00:00Z"},
        {"eventType": "login", "userId": None, "timestamp": 1_700_000_000},
        {"eventType": "document_created", "ownerId": "u1", "timestamp": "2024-03-07T09:30:00Z"},
    ]


def _random_events(seed: int, n: int) -> list[dict]:
    rng = random.Random(seed)
    events = []
    for i in range(n):
        etype = rng.choice(EVENT_TYPES)
        event: dict = {"eventType": etype, "eventId": f"e{i}"}
        for field in rng.sample(USER_FIELDS, rng.randint(0, 2)):
            event[field] = rng.choice([f"u{rng.randint(1, 40)}", "", None])
        if rng.random() < 0.8:
            event["documentId"] = rng.choice([f"d{rng.randint(1, 30)}", None])
        if rng.random() < 0.8:
            event["fileId"] = rng.choice([f"f{rng.randint(1, 30)}", None])
        if etype == "file_uploaded" and rng.random() < 0.9:
            event["sizeBytes"] = rng.choice([rng.randint(0, 10**7), None])
        if rng.random() < 0.9:
            event["timestamp"] = rng.choice(
                [
                    f"2024-03-07T{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00Z",
                    f"2024-03-07T{rng.randint(0, 23):02d}:00:00+02:00",
                    "garbage",
                    None,
                ]
            )
        events.append(event)
    return events


def _canonical(payload) -> str:
    return json.dumps(payload, indent=2)


# ---- S3 key formats -------------------------------------------------------


class TestS3KeyFormats:
    def test_partition_key_matches_legacy_template(self, legacy_analytics_source, report_date):
        match = re.search(
            r'partition_key = "([^"]+)" % \(analytics_prefix, ([^)]+)\)', legacy_analytics_source
        )
        assert match
        template, args = match.groups()
        assert template == "%s/year=%s/month=%s/day=%s"
        assert args.replace(" ", "") == "ds[:4],ds[5:7],ds[8:10]"
        ds = report_date
        assert partition_key(PREFIX, ds) == template % (PREFIX, ds[:4], ds[5:7], ds[8:10])
        assert partition_key(PREFIX, ds) == "analytics/daily/year=2024/month=03/day=07"

    def test_object_keys_match_legacy_templates(self, legacy_analytics_source, report_date):
        legacy_partition = "analytics/daily/year=2024/month=03/day=07"
        for legacy_var, fn in (
            ("summary_key", summary_key),
            ("hourly_key", hourly_breakdown_key),
            ("users_key", top_users_key),
        ):
            match = re.search(rf'{legacy_var} = "([^"]+)" % partition_key', legacy_analytics_source)
            assert match, legacy_var
            assert fn(PREFIX, report_date) == match.group(1) % legacy_partition

        assert summary_key(PREFIX, report_date) == f"{legacy_partition}/summary.json.gz"
        assert (
            hourly_breakdown_key(PREFIX, report_date)
            == f"{legacy_partition}/hourly_breakdown.json.gz"
        )
        assert top_users_key(PREFIX, report_date) == f"{legacy_partition}/top_users.jsonl.gz"

    def test_report_key_matches_legacy_template(self, legacy_analytics_source, report_date):
        match = re.search(r'report_key = "([^"]+)" % ds', legacy_analytics_source)
        assert match
        assert analytics_report_key(report_date) == match.group(1) % report_date
        assert analytics_report_key(report_date) == "reports/analytics/daily/2024-03-07/report.json"


# ---- Serialisation ----------------------------------------------------------


class TestEncoding:
    def test_gzip_json_uses_indent_2_like_legacy(self):
        payload = {"b": 1, "a": [1, 2]}
        assert gzip.decompress(encode_gzip_json(payload)) == json.dumps(payload, indent=2).encode()

    def test_gzip_jsonl_one_compact_row_per_line(self):
        rows = [{"user_id": "u1", "actions": {"login": 2}, "total": 2}, {"user_id": "u2"}]
        body = gzip.decompress(encode_gzip_jsonl(rows))
        assert body == b"".join(json.dumps(r).encode() + b"\n" for r in rows)

    def test_report_json_uses_indent_2_like_legacy(self):
        assert encode_json({"x": 1}) == b'{\n  "x": 1\n}'


# ---- SQL --------------------------------------------------------------------


class TestPostgresUpsert:
    def test_sql_is_identical_to_legacy(self, legacy_analytics_source):
        match = re.search(r'upsert_sql = """(.*?)"""', legacy_analytics_source, re.S)
        assert match
        legacy_sql = match.group(1)
        assert " ".join(ANALYTICS_UPSERT_SQL.split()) == " ".join(legacy_sql.split())

    def test_sql_targets_legacy_table_with_12_placeholders(self):
        assert "INSERT INTO analytics_daily_summary" in ANALYTICS_UPSERT_SQL
        assert ANALYTICS_UPSERT_SQL.count("%s") == 12
        assert "ON CONFLICT (report_date) DO UPDATE SET" in ANALYTICS_UPSERT_SQL

    def test_parameter_order_matches_legacy_cursor_execute(self, legacy_analytics_source):
        match = re.search(
            r"cursor\.execute\(upsert_sql, \((.*?)\)\)", legacy_analytics_source, re.S
        )
        assert match
        legacy_args = [a.strip() for a in match.group(1).split(",") if a.strip()]
        assert legacy_args[0] == "ds"
        legacy_columns = [re.fullmatch(r'summary\["(\w+)"\]', a).group(1) for a in legacy_args[1:]]
        assert list(SUMMARY_COLUMNS) == legacy_columns

        summary = {col: i + 1 for i, col in enumerate(SUMMARY_COLUMNS)}
        params = summary_upsert_params("2024-03-07", summary)
        assert params == ("2024-03-07", *range(1, 12))
        assert len(params) == ANALYTICS_UPSERT_SQL.count("%s")


# ---- Event normalisation ----------------------------------------------------


class TestNormalisation:
    def test_dynamodb_decimals_become_native_numbers(self):
        item = {"sizeBytes": Decimal("2048"), "ratio": Decimal("0.5"), "userId": "u1", "n": None}
        out = normalize_dynamodb_item(item)
        assert out == {"sizeBytes": 2048, "ratio": 0.5, "userId": "u1", "n": None}
        assert type(out["sizeBytes"]) is int and type(out["ratio"]) is float

    def test_event_type_resolution(self):
        assert resolve_event_type({"eventType": "login"}) == "login"
        assert resolve_event_type({"event_type": "login"}) == "login"
        assert resolve_event_type({}) == "unknown"

    def test_user_id_precedence_matches_legacy_column_order(self):
        event = {f: f"{f}-val" for f in USER_FIELDS}
        assert resolve_user_id(event) == "ownerId-val"
        del event["ownerId"]
        assert resolve_user_id(event) == "editedBy-val"
        assert resolve_user_id({"ownerId": "", "userId": None, "authorId": "a"}) == "a"
        assert resolve_user_id({"ownerId": "", "userId": None}) == "unknown"

    @pytest.mark.parametrize(
        ("timestamp", "expected"),
        [
            ("2024-03-07T09:15:00Z", "09"),
            ("2024-03-07T23:00:00-05:00", "23"),
            ("2024-03-07 07:00:00", "07"),
            ("garbage", "00"),
            (None, "00"),
            (1700000000, "00"),
        ],
    )
    def test_parse_hour(self, timestamp, expected):
        assert parse_hour(timestamp) == expected


# ---- Aggregation parity vs legacy pandas ------------------------------------


def _assert_same_aggregates(events: list[dict]) -> None:
    legacy = legacy_aggregate(events)
    new = aggregate_events(events)
    for section in (
        "summary",
        "hourly_breakdown",
        "user_summaries",
        "document_metrics",
        "file_metrics",
    ):
        assert _canonical(new[section]) == _canonical(legacy[section]), section
    # gzip payloads are byte-identical too
    assert encode_gzip_json(new["summary"]) == encode_gzip_json(legacy["summary"])
    assert encode_gzip_jsonl(new["user_summaries"]) == encode_gzip_jsonl(legacy["user_summaries"])


class TestAggregationParity:
    def test_hand_written_sample(self):
        _assert_same_aggregates(_sample_events())

    def test_hand_written_sample_expected_values(self):
        result = aggregate_events(_sample_events())
        assert result["summary"] == {
            "active_users": 4,
            "active_documents": 2,
            "active_files": 2,
            "total_events": 11,
            "documents_created": 2,
            "documents_edited": 2,
            "comments_added": 1,
            "files_uploaded": 2,
            "files_shared": 1,
            "files_deleted": 1,
            "bytes_uploaded": 3072,
        }
        assert list(result["hourly_breakdown"]) == ["00", "09", "14", "23"]
        assert result["hourly_breakdown"]["09"] == {
            "document_created": 2,
            "document_edited": 1,
            "login": 1,
        }
        assert result["user_summaries"][0] == {
            "user_id": "u1",
            "actions": {"document_created": 2, "file_uploaded": 1, "file_shared": 1},
            "total": 4,
        }
        assert result["document_metrics"] == {"created": 2, "edited": 2, "comments": 1}
        assert result["file_metrics"] == {
            "uploaded": 2,
            "shared": 1,
            "deleted": 1,
            "bytes_uploaded": 3072,
        }

    @pytest.mark.parametrize("seed", range(8))
    def test_randomised_events(self, seed):
        _assert_same_aggregates(_random_events(seed, 400))

    def test_snake_case_event_type_only(self):
        events = [
            {"event_type": "file_uploaded", "userId": "u1", "fileId": "f1", "sizeBytes": 5},
            {"event_type": "file_uploaded", "userId": "u1", "fileId": "f1", "sizeBytes": 7},
        ]
        _assert_same_aggregates(events)
        assert aggregate_events(events)["summary"]["bytes_uploaded"] == 12

    def test_no_event_type_field_at_all(self):
        events = [{"userId": "u1"}, {"userId": "u2"}, {"other": 1}]
        _assert_same_aggregates(events)
        assert aggregate_events(events)["hourly_breakdown"] == {"00": {"unknown": 3}}

    def test_top_users_capped_at_100_and_sorted_desc_stable(self):
        events = []
        for i in range(150):
            events.extend({"eventType": "login", "userId": f"u{i:03d}"} for _ in range(150 - i))
        _assert_same_aggregates(events)
        users = aggregate_events(events)["user_summaries"]
        assert len(users) == 100
        assert users[0] == {"user_id": "u000", "actions": {"login": 150}, "total": 150}
        assert [u["total"] for u in users] == sorted((u["total"] for u in users), reverse=True)

    def test_unknown_user_is_counted_in_top_users_but_not_active_users(self):
        events = [
            {"eventType": "login"},
            {"eventType": "login"},
            {"eventType": "login", "userId": "u1"},
        ]
        _assert_same_aggregates(events)
        result = aggregate_events(events)
        assert result["summary"]["active_users"] == 1
        assert result["user_summaries"][0]["user_id"] == "unknown"

    def test_bytes_uploaded_treats_null_size_as_zero(self):
        events = [
            {"eventType": "file_uploaded", "userId": "u1", "fileId": "f1", "sizeBytes": None},
            {"eventType": "file_uploaded", "userId": "u1", "fileId": "f2", "sizeBytes": 10},
            {"eventType": "file_shared", "userId": "u1", "fileId": "f3", "sizeBytes": 999},
        ]
        _assert_same_aggregates(events)
        assert aggregate_events(events)["summary"]["bytes_uploaded"] == 10


# ---- Report -----------------------------------------------------------------


class TestReport:
    def test_peak_hour_matches_legacy(self):
        events = _sample_events()
        legacy = legacy_aggregate(events)
        assert find_peak_hour(aggregate_events(events)["hourly_breakdown"]) == legacy["peak_hour"]
        assert find_peak_hour({}) is None

    def test_report_layout_matches_legacy(self, report_date):
        events = _sample_events()
        legacy = legacy_aggregate(events)
        generated_at = "2024-03-07T02:05:00+00:00"
        report = build_analytics_report(
            report_date=report_date,
            generated_at=generated_at,
            aggregates=aggregate_events(events),
        )
        expected = {
            "report_type": "daily_analytics",
            "report_date": report_date,
            "generated_at": generated_at,
            "summary": legacy["summary"],
            "highlights": {
                "peak_hour": legacy["peak_hour"],
                "most_active_users": legacy["most_active_users"],
            },
            "document_metrics": legacy["document_metrics"],
            "file_metrics": legacy["file_metrics"],
        }
        assert _canonical(report) == _canonical(expected)
        assert len(report["highlights"]["most_active_users"]) <= 5
