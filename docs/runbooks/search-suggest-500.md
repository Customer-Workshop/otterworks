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

3. Confirm the failing request pattern: `GET /api/v1/search/suggest?q=<prefix>` returns
   `500` while `GET /api/v1/search/?q=<prefix>` still returns `200`. Only the suggest
   handler runs the ranking-score sort.

## Root Cause

The suggest handler sorted MeiliSearch hits with `hit["_rankingScore"]`. MeiliSearch only
includes `_rankingScore` in a hit when the query sets `showRankingScore: true`; the suggest
query did not, so the lookup raised `KeyError` on the first hit. The sort ran outside the
handler's `try/except`, so the exception surfaced as a 500 instead of degrading to an empty
suggestion list.

## Resolution Steps

1. Immediate mitigation: clear the chaos flag if it is set
   (`redis-cli DEL chaos:search-service:suggest_500`, or `scripts/inject-bug.sh <ID> reset`
   on a tenant). The error rate drops within one scrape interval.
2. Code fix (`services/search-service`):
   - `MeiliSearchService.suggest` requests `showRankingScore: true`, reads the score with a
     `0.0` default, and sorts the merged hits itself.
   - The `/suggest` handler has a single code path inside `try/except`, so any backend error
     returns `200` with `suggestions: []` rather than a 5xx.
3. Verify: `cd services/search-service && .venv/bin/pytest tests/test_search_api.py`, then
   watch the `SearchSuggestHighErrorRate` panel clear.

## Post-Incident

- Autocomplete is best-effort: the handler must never return a 5xx for a ranking or
  backend error. The tests in `tests/test_search_api.py::TestSuggestEndpoint` pin this.
- Any new field read from a MeiliSearch hit must be requested explicitly
  (`attributesToRetrieve` / `showRankingScore`) and read with a default.
