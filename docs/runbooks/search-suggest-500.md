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

3. Confirm the failing code path: the ranking-score enrichment in
   `services/search-service/app/api/search.py::suggest()` indexes `_rankingScore`
   directly on each hit. MeiliSearch only returns `_rankingScore` when the query sets
   `showRankingScore: true`, so the lookup raises and the handler returns 500.

## Resolution Steps

1. If the chaos flag is set, clear it (`redis-cli DEL chaos:search-service:suggest_500` or
   `scripts/inject-bug.sh <ID> reset`) — the error rate should drop within a minute.
2. Ship the code fix: request `showRankingScore` in `MeiliSearchService.suggest()`, read the
   score with `.get()` (defaulting to `0.0`), and keep the ranking inside the handler's
   `try/except` so a backend failure degrades to an empty `200` instead of a `500`.
3. Verify: `curl "$SEARCH_URL/api/v1/search/suggest?q=te"` returns `200` and the
   `SearchSuggestHighErrorRate` alert resolves.

## Post-Incident

- Any new field read from a MeiliSearch hit must be requested explicitly and read with
  `.get()`; hits are not guaranteed to carry optional metadata.
- Keep the whole `suggest()` body inside the error handler — autocomplete is best-effort
  and must never surface a 5xx to the web app search bar.
