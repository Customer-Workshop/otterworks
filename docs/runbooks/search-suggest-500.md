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

3. Reproduce directly against the service (bypassing the gateway):
   ```
   curl -s -o /dev/null -w "%{http_code}\n" "http://search-service:8087/api/v1/search/suggest?q=te"
   ```
4. Inspect `services/search-service/app/api/search.py::suggest` and
   `app/services/meilisearch_client.py::MeiliSearchService.suggest` for any code that
   indexes `hit["_rankingScore"]` without requesting `showRankingScore` from MeiliSearch.

## Resolution Steps

1. Immediate mitigation: clear the chaos flag so traffic falls back to the healthy path.
   ```
   redis-cli DEL chaos:search-service:suggest_500
   ```
2. Root-cause fix (code): ranking must be done inside `MeiliSearchService.suggest`, which
   requests `showRankingScore: true` and reads the score with `.get()` (default `0.0`) so
   hits without a score never raise. The handler keeps all MeiliSearch calls inside its
   `try/except` and degrades to `{"suggestions": []}` with HTTP 200 on any backend error.
3. Redeploy search-service and confirm the alert resolves:
   ```
   kubectl rollout restart deployment/search-service -n otterworks
   kubectl rollout status deployment/search-service -n otterworks
   ```
4. Verify: repeat the `curl` from step 3 above (expect `200`) and check the 5xx panel on the
   Chaos Scenarios dashboard returns below 5%.

## Post-Incident

- Regression coverage lives in
  `services/search-service/tests/test_search_api.py::TestSuggestEndpoint`
  (`test_suggest_ranked_by_score`, `test_suggest_missing_ranking_score`,
  `test_suggest_backend_error_degrades_gracefully`).
- Any new response-enrichment step in a request handler must sit inside the existing
  `try/except` and treat MeiliSearch metadata fields (`_rankingScore`, `_formatted`, ...)
  as optional.
