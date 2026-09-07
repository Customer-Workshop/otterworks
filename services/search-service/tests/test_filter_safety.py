"""Tests for MeiliSearch filter construction and backend-error handling."""

from __future__ import annotations

import meilisearch
import pytest

from app.services.meilisearch_client import InvalidSearchRequest, MeiliSearchService


def _api_error(message: str) -> meilisearch.errors.MeilisearchApiError:
    class _Resp:
        status_code = 400
        text = f'{{"message": "{message}", "code": "invalid_search_filter"}}'

        @staticmethod
        def json():
            return {"message": message, "code": "invalid_search_filter"}

    return meilisearch.errors.MeilisearchApiError(message, _Resp())


BACKEND_TEXT = "Attribute `owner_id` is not filterable. Available filterable attributes are: `type`"


def _filters(mock_meilisearch_client) -> list[str]:
    mock_index = mock_meilisearch_client.index.return_value
    return [call.args[1].get("filter", "") for call in mock_index.search.call_args_list]


class TestEscaping:
    def test_quote_and_backslash_escaped(self):
        assert MeiliSearchService._escape('a"b\\c') == 'a\\"b\\\\c'

    def test_owner_id_injection_cannot_break_out(self, meilisearch_service, mock_meilisearch_client):
        payload = 'x" OR owner_id != "'
        meilisearch_service.search("q", owner_id=payload)
        for f in _filters(mock_meilisearch_client):
            assert f == 'owner_id = "x\\" OR owner_id != \\""'

    def test_type_must_be_known(self, meilisearch_service):
        with pytest.raises(InvalidSearchRequest) as exc:
            meilisearch_service.search("q", doc_type='document" OR type != "')
        assert "type" in str(exc.value)
        assert "OR" not in str(exc.value)

    def test_control_characters_rejected(self, meilisearch_service):
        with pytest.raises(InvalidSearchRequest):
            meilisearch_service.search("q", owner_id="user\n OR 1")

    def test_overlong_value_rejected(self, meilisearch_service):
        with pytest.raises(InvalidSearchRequest):
            meilisearch_service.search("q", owner_id="a" * 300)

    @pytest.mark.parametrize("bad", ["2024-01-01\" OR x", "yesterday", "2024-1-1", 20240101])
    def test_dates_must_be_iso(self, meilisearch_service, bad):
        with pytest.raises(InvalidSearchRequest):
            meilisearch_service.advanced_search("q", date_from=bad)

    @pytest.mark.parametrize("good", ["2024-01-01", "2024-01-01T10:20:30Z", "2024-01-01T10:20:30.123+02:00"])
    def test_valid_dates_accepted(self, meilisearch_service, mock_meilisearch_client, good):
        meilisearch_service.advanced_search("q", date_from=good, date_to=good)
        for f in _filters(mock_meilisearch_client):
            assert f'created_at >= "{good}"' in f and f'created_at <= "{good}"' in f

    @pytest.mark.parametrize("bad", ["finance", [1, 2], [""], ["a"] * 51, {"a": 1}])
    def test_tags_must_be_string_list(self, meilisearch_service, bad):
        with pytest.raises(InvalidSearchRequest):
            meilisearch_service.advanced_search("q", tags=bad)

    def test_tags_escaped(self, meilisearch_service, mock_meilisearch_client):
        meilisearch_service.advanced_search("q", tags=['fin" OR 1'])
        for f in _filters(mock_meilisearch_client):
            assert '(tags = "fin\\" OR 1")' in f


class TestBackendErrorsNeverLeak:
    def test_search_hides_backend_text(self, meilisearch_service, mock_meilisearch_client):
        mock_meilisearch_client.index.return_value.search.side_effect = _api_error(BACKEND_TEXT)
        with pytest.raises(InvalidSearchRequest) as exc:
            meilisearch_service.search("q", owner_id="u")
        assert "filterable" not in str(exc.value)
        assert "owner_id" not in str(exc.value)

    def test_advanced_search_hides_backend_text(self, meilisearch_service, mock_meilisearch_client):
        mock_meilisearch_client.index.return_value.search.side_effect = _api_error(BACKEND_TEXT)
        with pytest.raises(InvalidSearchRequest) as exc:
            meilisearch_service.advanced_search("q", tags=["a"])
        assert "filterable" not in str(exc.value)


class TestApiErrorResponses:
    def test_search_400_is_generic(self, client, mock_meilisearch_client):
        mock_meilisearch_client.index.return_value.search.side_effect = _api_error(BACKEND_TEXT)
        resp = client.get("/api/v1/search/?q=' OR 1=1 --")
        assert resp.status_code == 400
        body = resp.get_data(as_text=True)
        assert "filterable" not in body
        assert "Available" not in body
        assert resp.get_json()["error"] == "Invalid search request"

    def test_advanced_400_is_generic(self, client, mock_meilisearch_client):
        mock_meilisearch_client.index.return_value.search.side_effect = _api_error(BACKEND_TEXT)
        resp = client.post("/api/v1/search/advanced", json={"q": "x", "tags": ["a"]})
        assert resp.status_code == 400
        assert "filterable" not in resp.get_data(as_text=True)

    def test_unexpected_exception_is_generic(self, client, mock_meilisearch_client):
        mock_meilisearch_client.index.return_value.search.side_effect = RuntimeError(
            "psycopg2.errors.SyntaxError: syntax error at or near"
        )
        resp = client.get("/api/v1/search/?q=x")
        assert resp.status_code == 500
        assert "psycopg2" not in resp.get_data(as_text=True)
        assert "syntax error" not in resp.get_data(as_text=True)

    def test_invalid_type_param(self, client):
        resp = client.get('/api/v1/search/?q=x&type=document" OR 1')
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "Invalid type parameter"

    def test_advanced_rejects_non_object_body(self, client):
        resp = client.post("/api/v1/search/advanced", json=["not", "an", "object"])
        assert resp.status_code == 400

    def test_advanced_invalid_date(self, client):
        resp = client.post("/api/v1/search/advanced", json={"q": "x", "date_from": "1' OR '1'='1"})
        assert resp.status_code == 400
        assert "OR" not in resp.get_json()["error"]
