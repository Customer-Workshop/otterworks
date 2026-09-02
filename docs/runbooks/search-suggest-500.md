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

3. Confirm the failing code path: `suggest()` in `services/search-service/app/api/search.py`
   sorting hits on `hit["_rankingScore"]`. MeiliSearch only includes `_rankingScore` when the
   request sets `showRankingScore: true`; without it every hit raises `KeyError` and the
   handler returns 500.

## Resolution Steps

1. Roll back search-service to the last image that did not include the ranking-score
   enrichment, or deploy the fix below.
2. Fix: `MeiliSearchService.suggest` requests `showRankingScore: true`, reads the score with
   `hit.get("_rankingScore")` (defaulting to 0.0), and the `/suggest` handler wraps the whole
   lookup in the existing `try/except` so backend errors degrade to an empty 200 instead of
   a 5xx. The response contract stays `{"suggestions": string[], "query": string}`.
3. Verify: `curl "$SEARCH_URL/api/v1/search/suggest?q=te"` returns 200 and the
   `SearchSuggestHighErrorRate` alert resolves within one evaluation window.

## Post-Incident

- Regression tests in `services/search-service/tests/test_search_api.py`
  (`TestSuggestEndpoint`) cover hits with and without `_rankingScore` and a backend failure.
- Any new "enrichment" step on a hot read path must stay inside the handler's error
  boundary and must not change the response shape consumed by `frontend/client-app`.
