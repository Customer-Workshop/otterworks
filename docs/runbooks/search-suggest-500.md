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

3. Correlate the first `KeyError`/`TypeError` in `suggest()` with the most recent
   search-service deployment (`kubectl rollout history deploy/search-service -n otterworks`).

## Root Cause

The `/suggest` handler had a ranking-score enrichment branch that sorted suggestions with
`s["_rankingScore"]`. MeiliSearch only returns `_rankingScore` when `showRankingScore: true`
is passed in the search request, and `MeiliSearchService.suggest()` returns plain strings,
so the lookup raised `KeyError`/`TypeError` outside the handler's `try/except` and every
request on that path returned 500.

## Resolution Steps

1. Roll out a search-service build that requests `showRankingScore` and sorts on
   `hit.get("_rankingScore", 0)` inside `MeiliSearchService.suggest()`; the handler's
   `try/except` guarantees `/suggest` degrades to `{"suggestions": []}` instead of a 5xx.
2. If the chaos flag is set, clear it: `redis-cli DEL chaos:search-service:suggest_500`
   (or `scripts/inject-bug.sh <ID> reset` for a tenant).
3. Confirm recovery: `curl -s "$SEARCH_URL/api/v1/search/suggest?q=te"` returns 200 and the
   `SearchSuggestHighErrorRate` alert resolves within one evaluation window.

## Post-Incident

- Any new field read from a MeiliSearch hit must use `.get()` with a default and be
  covered by a unit test that omits the field.
- Enrichment/ranking changes to `/suggest` must stay inside the handler's `try/except`.
