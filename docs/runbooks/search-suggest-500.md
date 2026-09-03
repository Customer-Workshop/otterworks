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

3. Reproduce against a pod directly (bypassing the gateway) and confirm the status code:
   ```
   kubectl exec deploy/search-service -n otterworks -- curl -s -o /dev/null -w '%{http_code}\n' 'http://localhost:8087/api/v1/search/suggest?q=te'
   ```
4. Check whether a recent deployment touched `services/search-service/app/api/search.py` or
   `app/services/meilisearch_client.py` (`suggest()` ranking pipeline).

## Root Cause

The autocomplete ranking pipeline sorted suggestions with `s["_rankingScore"]`. MeiliSearch
only includes `_rankingScore` on hits when the search request sets `showRankingScore: true`,
so the lookup raised `KeyError` and the handler returned HTTP 500 for every request. The
enrichment path also bypassed the handler's `try/except`, so the failure was not degraded to
an empty suggestion list like other backend errors.

## Resolution Steps

1. Deploy a search-service build in which `MeiliSearchService.suggest()` requests
   `showRankingScore: true`, reads the score with `hit.get("_rankingScore", 0.0)`, and runs
   inside the handler's `try/except` so any backend failure yields `200 {"suggestions": []}`.
2. If the chaos flag is set, clear it (`scripts/inject-bug.sh <tenant> reset`, or
   `redis-cli DEL chaos:search-service:suggest_500`).
3. Verify: the `SearchSuggestHighErrorRate` alert resolves and
   `GET /api/v1/search/suggest?q=te` returns 200 with a JSON array of strings.

## Post-Incident

- Regression tests in `services/search-service/tests/test_search_api.py::TestSuggestEndpoint`
  cover ranking order, hits without `_rankingScore`, and backend errors returning 200.
- Any future enrichment of suggestions must stay inside `MeiliSearchService.suggest()` so
  the handler's fail-soft behaviour applies.
