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

3. Reproduce against the affected pod and confirm the response code:
   ```
   kubectl port-forward svc/search-service 8087:8087 -n otterworks
   curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8087/api/v1/search/suggest?q=te"
   ```

## Root Cause

The suggest handler had a ranking-score enrichment step that indexed
`hit["_rankingScore"]` directly. MeiliSearch only returns `_rankingScore` when the
search request sets `showRankingScore: true`; the request did not, so the lookup
raised `KeyError` and the handler returned 500. The step also ran outside the
handler's `try`/`except`, so the failure was not caught and degraded.

## Resolution Steps

1. Roll out the search-service build that includes the fix in
   `services/search-service/app/services/meilisearch_client.py` (`suggest()` requests
   `showRankingScore` and falls back to a score of `0.0` when the field is missing) and
   `services/search-service/app/api/search.py` (all suggest work runs inside the guarded
   path, so any backend error returns an empty list with 200 instead of a 5xx).
2. If the chaos flag is set, clear it: `redis-cli DEL chaos:search-service:suggest_500`.
3. Confirm the alert clears: the search-service 5xx rate should drop below 5% within
   one evaluation window, and `curl .../suggest?q=te` should return `200`.

## Post-Incident

- Regression tests in `services/search-service/tests/test_search_api.py`
  (`TestSuggestEndpoint`) cover hits with, without, and with `null` `_rankingScore`,
  an empty index, and a MeiliSearch failure.
- Any new field read from a MeiliSearch hit must use `.get()` with a default and be
  covered by a test that omits the field.
