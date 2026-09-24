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

3. Reproduce locally against the service: `curl -s -o /dev/null -w '%{http_code}\n' "http://localhost:8087/api/v1/search/suggest?q=te"` — a 500 confirms the handler is crashing rather than MeiliSearch being down.

## Root Cause

The suggest handler sorted suggestions by `_rankingScore`, but MeiliSearch only
returns that field when the search request sets `showRankingScore: true`. The
sort ran outside the handler's `try/except`, so a missing key (or a plain-string
suggestion) raised `KeyError`/`TypeError` and surfaced as a 500.

## Resolution Steps

1. If the chaos flag is set, clear it: `redis-cli DEL chaos:search-service:suggest_500`
   (or `scripts/inject-bug.sh <ID> reset` for a tenant).
2. Deploy a search-service build where `MeiliSearchService.suggest` requests
   `showRankingScore` and tolerates hits without a score, and where the ranking
   step runs inside the handler's error boundary so failures degrade to an empty
   suggestion list instead of a 500.
3. Confirm `SearchSuggestHighErrorRate` resolves and the search-service 5xx panel
   drops back to baseline.

## Post-Incident

<!-- TODO -->
