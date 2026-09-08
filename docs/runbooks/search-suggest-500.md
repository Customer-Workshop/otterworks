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

3. Reproduce directly against the service, bypassing the gateway:
   ```
   curl -i "http://search-service:8087/api/v1/search/suggest?q=te"
   ```
   A `500` with `KeyError: '_rankingScore'` or `TypeError: string indices must be integers`
   in the logs confirms the ranking-score enrichment path is crashing.

## Root Cause

`MeiliSearchService.suggest()` returns plain title strings, and MeiliSearch only includes
`_rankingScore` in hits when `showRankingScore: true` is sent. The ranking-score sort in the
`/suggest` handler indexed `s["_rankingScore"]` on those values outside the handler's
`try/except`, so any request with results (or an empty index) raised and returned a 500.

## Resolution Steps

1. If the chaos flag is set, clear it to stop the bleeding immediately:
   ```
   redis-cli DEL chaos:search-service:suggest_500
   ```
2. Deploy the fix: ranking now happens inside `MeiliSearchService.suggest()`, which requests
   `showRankingScore`, tolerates hits with no score, and stays inside the handler's
   graceful-degradation `try/except` (empty suggestion list instead of a 5xx).
3. Confirm recovery: `SearchSuggestHighErrorRate` resolves and
   `curl ".../api/v1/search/suggest?q=te"` returns `200` with a `suggestions` array.

## Post-Incident

- `tests/test_search_api.py::TestSuggestEndpoint` covers ranked ordering, hits without
  `_rankingScore`, and MeiliSearch failures returning 200 with an empty list.
- Autocomplete is best-effort: any future enrichment of `/suggest` must live inside the
  handler's `try/except` so a ranking bug degrades to "no suggestions" rather than a 5xx.
