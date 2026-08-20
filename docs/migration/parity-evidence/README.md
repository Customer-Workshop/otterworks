# Pinned parity evidence

The three JSON files here are the full output of `tests/parity/portal/replay.py` for each
context, recorded on freshly started backends with:

- **reference (`--legacy`)**: `otterworks/legacy-portal:pre-retirement-c07b93bc`, the monolith
  built from commit `c07b93bc` — the last commit where it still served all three contexts;
- **candidate (`--candidate`)**: the extracted services from this branch, `announcements`
  8101, `user-preferences` 8102, `feedback` 8103.

Results: announcements `60/60`, user-preferences `47/47`, feedback `61/61` identical.

These transcripts exist because the deployed monolith is now a shell that returns `404` for
these routes, so a replay against `legacy-portal:8095` proves nothing. They are the
monolith-backed evidence of record; the harness that produced them is unchanged. To re-record,
follow `docs/migration/decommission.md`. The scenarios mutate state, so both sides must be
recreated before a run — replaying twice against the same containers compares two
differently-accumulated datasets and reports spurious diffs.
