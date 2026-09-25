# Runbook: Search Autocomplete 500 Errors

**Severity:** Critical

## Alert

`SearchSuggestHighErrorRate` -- fires when search-service 5xx rate exceeds 5% over a 1-minute window.

## Symptoms

- Autocomplete suggestions stop appearing in the web app search bar.
- The Chaos Scenarios dashboard shows elevated error rates on the search-service panel.
- Application logs contain `KeyError: '_rankingScore'` in the suggest endpoint handler.

## Investigation Steps

1. Confirm the error in search-service logs:
   ```
   kubectl logs -l app=search-service --tail=100 -n otterworks | grep -i "KeyError\|rankingScore\|500"
   ```
2. Check whether the chaos flag `chaos:search-service:suggest_500` is set in Redis:
   ```
   redis-cli EXISTS chaos:search-service:suggest_500
   ```

3. Confirm the failure mode with one request (the handler crashed before its
   `except` block, so the response is Flask's HTML 500 page, not JSON):
   ```
   curl -si 'http://localhost:8087/api/v1/search/suggest?q=te' | head -1
   ```

## Resolution Steps

1. Immediate mitigation: clear the chaos flag so the service falls back to the
   unranked path (`redis-cli DEL chaos:search-service:suggest_500`).
2. Code fix (`services/search-service`):
   - `MeiliSearchService.suggest` asks MeiliSearch for the score
     (`showRankingScore: true`), merges hits from both indices, and sorts with
     `hit.get("_rankingScore")` (unscored hits sort last).
   - `GET /suggest` has a single code path inside `try/except`; any backend
     failure logs `suggest_failed` and returns `200 {"suggestions": []}` so the
     autocomplete box degrades to empty rather than paging.
3. Verify: `cd services/search-service && .venv/bin/pytest -q tests/test_search_api.py -k suggest`,
   then watch `SearchSuggestHighErrorRate` resolve in Grafana.

## Post-Incident

- The `/suggest` ranking pipeline read `_rankingScore` from a result that was
  never asked to include it, and the enrichment ran outside the handler's
  `try/except`. Any new hit-shape assumption in search-service should be pinned
  by a unit test with a mocked MeiliSearch response (see
  `tests/test_search_api.py::TestSuggestEndpoint`).
