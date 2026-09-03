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

1. If the chaos flag is set, clear it: `scripts/inject-bug.sh <ID> reset` (or `redis-cli DEL chaos:search-service:suggest_500`).
2. Confirm `search-service` is running a build where `MeiliSearchService.suggest()` requests
   `showRankingScore: true` and tolerates hits without `_rankingScore`; the `/suggest` handler
   must catch backend errors and return an empty `200` rather than a `500`.
3. Verify: `curl "$SEARCH_URL/api/v1/search/suggest?q=te"` returns `200` and the
   `SearchSuggestHighErrorRate` alert resolves within one evaluation window.

## Post-Incident

<!-- TODO -->
