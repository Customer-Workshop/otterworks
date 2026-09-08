# Incident Summary: Search autocomplete intermittently returns errors / empty results

**Service:** search-service (`GET /api/v1/search/suggest`)
**Severity:** Critical (alert `SearchSuggestHighErrorRate`)
**Branch:** `workshop-ep-incident` (off `workshop`)

## What users saw

- Autocomplete suggestions stopped appearing. The web-app client wrapper
  (`frontend/client-app/src/lib/api.ts`, `searchApi.suggest`) expects a JSON
  `{ suggestions: string[] }`; instead the service returned Flask's default HTML
  `500 Internal Server Error` page, so the axios call rejected and any caller either surfaced
  an error or rendered nothing — not even the empty-list fallback the endpoint normally emits.
- The symptom was intermittent because the trigger is a Redis key with a TTL
  (`chaos:search-service:suggest_500`, default 3600s via `scripts/inject-bug.sh`): while the
  key existed every suggest call with `len(q) >= 2` failed; once it expired (or Redis was
  unreachable, since `_chaos_active()` swallows connection errors) suggest recovered on its
  own, which is why reports were sporadic.
- Search-service logs showed `KeyError: '_rankingScore'` (empty index) or
  `TypeError: string indices must be integers` (non-empty index) from the suggest handler.

## Root cause

`suggest()` in `services/search-service/app/api/search.py` had two code paths. When the
Redis flag `chaos:search-service:suggest_500` was set it ran a "ranking-score enrichment"
branch that:

1. Called `MeiliSearchService.suggest()`, which returns a `list[str]` of titles (already in
   MeiliSearch relevance order) — not raw hit dicts.
2. If that list was empty, replaced it with `[{}]`.
3. Sorted with `key=lambda s: s["_rankingScore"]`. `_rankingScore` is only emitted by
   MeiliSearch when `showRankingScore` is requested, and never on plain strings, so the sort
   raised `KeyError` (on `{}`) or `TypeError` (on a `str`).
4. Ran **outside** the `try/except` that protects the normal path, so the exception
   propagated to Flask and became an unhandled 500.

The normal path (flag unset) already degraded gracefully (200 + `[]` on any exception); the
ranking path did not.

## Blast radius

- Only `GET /api/v1/search/suggest`; full-text `/search`, `/advanced` and `/analytics` were
  unaffected.
- Only tenants whose own Redis held the flag (per-tenant Redis; flags never cross namespaces).
- Every suggest request in an affected tenant failed for the lifetime of the key, regardless
  of index contents. No data loss or corruption; the failure was read-only.

## Fix

`services/search-service/app/api/search.py`:

- The whole handler body — MeiliSearch lookup **and** optional ranking — now runs inside the
  single `try/except`, so any failure degrades to `200 {"suggestions": [], "query": q}` with a
  `suggest_failed` log line instead of a 500.
- The ranking step is a helper, `_rank_suggestions()`, that only re-orders when every entry
  carries a numeric `_rankingScore`; otherwise it logs `suggest_ranking_skipped` and returns
  the suggestions in their original (MeiliSearch relevance) order. The `[{}]` sentinel that
  forced a crash on an empty index is gone.
- The flag key is exposed as `SUGGEST_RANKING_FLAG` so tests and the bug catalog share one
  definition.

Regression tests (`tests/test_search_api.py`, `TestSuggestRankingFlag`, `TestRankSuggestions`)
pin the flag key and assert 200 + correct payload with the flag active for: hits without a
score, an empty index, and a MeiliSearch failure; plus unit coverage of the ranking helper.

## How to verify in a tenant

Deploy this branch to a tenant (pushing `workshop-<id>` ships it automatically via
`cd-tenant.yml`), then:

```bash
# 1. Baseline: suggestions work
curl -s "https://api-t-<ID>.<domain>/api/v1/search/suggest?q=te" -H "X-User-ID: <uid>"
# -> 200 {"query":"te","suggestions":[...]}

# 2. Inject the scenario into the tenant's own Redis (SETEX chaos:search-service:suggest_500 3600 1)
./scripts/inject-bug.sh <ID> search-suggest-500

# 3. Before the fix this returned an HTML 500; after the fix it must stay 200
curl -s -o /dev/null -w "%{http_code}\n" "https://api-t-<ID>.<domain>/api/v1/search/suggest?q=te" -H "X-User-ID: <uid>"
# -> 200, body {"query":"te","suggestions":[...]} (same list as step 1; order unchanged)
kubectl -n otterworks-<ID> logs deploy/search-service --tail=50 | grep -E "suggest_ranking_skipped|suggest_failed|KeyError"
# -> suggest_ranking_skipped (reason=ranking_score_missing); no KeyError / 500

# 4. Clear the flag and confirm the normal path is unchanged
./scripts/inject-bug.sh <ID> reset
```

The `SearchSuggestHighErrorRate` alert on the Chaos Scenarios dashboard should stay quiet
throughout step 3.

## Follow-ups

- `docs/runbooks/search-suggest-500.md` still has TODO resolution steps; point them at this
  summary.
- If relevance re-ranking is actually wanted, `MeiliSearchService.suggest()` should request
  `showRankingScore: true` and return scored hits rather than bare titles.
