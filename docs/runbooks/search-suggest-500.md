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

<!-- TODO: Complete investigation steps -->

## Resolution Steps

1. **Root cause:** the suggest handler's ranking-score enrichment sorted hits with
   `hit["_rankingScore"]`, but MeiliSearch only returns `_rankingScore` when the search
   request sets `showRankingScore: true`. The lookup raised `KeyError` and the handler
   returned HTTP 500 (the path also ran outside the endpoint's `try/except`).
2. **Fix:** `MeiliSearchService.suggest()` now requests `showRankingScore` and orders hits
   with `hit.get("_rankingScore", 0.0)`; the handler has a single code path inside
   `try/except`, so a MeiliSearch failure degrades to an empty suggestion list (200).
3. Clear the chaos flag if it is still set, then confirm the error rate drops:
   ```
   redis-cli DEL chaos:search-service:suggest_500
   curl -s -o /dev/null -w '%{http_code}\n' 'http://localhost:8087/api/v1/search/suggest?q=te'
   ```

## Post-Incident

<!-- TODO -->
