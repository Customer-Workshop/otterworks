# Data seam confirmation

Wave 0 evidence that the three contexts can each take their own database without a distributed
transaction, a shared table, or a synchronising read. The Confluence page *Bounded Contexts &
Seams* (space `LM`) asserts the seams; this is the check against the source tree, and it is the
precondition for every Wave 1 child.

**Verdict: all three seams are clean.** Each context owns exactly one table, nothing crosses,
and the couplings that remain are runtime and process couplings, not data couplings.

## 1. Table ownership

| Context | Schema (monolith) | Table | Key | Read/written by |
|---|---|---|---|---|
| Announcements | `announcements` | `announcement` | `id` identity | `announcements` package only |
| User preferences | `user_preferences` | `user_preference` | `user_id` natural | `userpreferences` package only |
| Feedback | `feedback` | `feedback` | `id` identity | `feedback` package only |

Three tables, three packages, one owner each. The monolith already keeps them in **separate
schemas** — the seam was drawn in the schema layout before this migration, which is why the
split is cheap.

## 2. What is absent (the part that matters)

Checked across `services/legacy-portal/src/main/java`:

- **No foreign keys** between contexts — no `@ManyToOne`, `@OneToMany`, `@OneToOne`,
  `@JoinColumn` or `@JoinTable` anywhere in the module.
- **No shared tables.** No table is written by more than one package.
- **No cross-context joins.** Every repository is a Spring Data interface over its own entity;
  there is no `@Query` with a join and no native SQL at all.
- **No cross-context Java references.** No class under one context package imports a class from
  another. The only shared types are the Spring/Jakarta libraries and
  `GlobalExceptionHandler`, `HealthController` and `PortalBrandingSettings` in the `common`
  package.
- **No cross-context transaction.** No request path writes two contexts, so nothing depends on
  the single `EntityManager` making two tables atomic.
- **No shared identifier integrity.** `user_id` appears in both `user_preference` and
  `feedback`, but it is an opaque caller-supplied string with **no table behind it in either
  place** and no constraint linking them. Splitting cannot break a relationship that the
  database never enforced. It does make the absence explicit: after the split, two services
  hold the same unvalidated key with nothing reconciling them — an existing property, now
  visible.

## 3. What is actually shared (and how each is severed)

These are the real couplings. None is a data seam; all are removed by the split.

| Coupling | Today | After extraction |
|---|---|---|
| Datasource + Hikari pool | one pool for all three contexts; feedback's full-table scans starve announcements | one pool per service |
| Hibernate persistence unit | one `EntityManagerFactory`, one `ddl-auto: update` | one per service, Flyway, `ddl-auto: none` |
| Database role | a single role with rights on all three schemas | one role per database, rights to its own tables only |
| `GlobalExceptionHandler` | one advice defines both error envelopes | copied verbatim into `portal-common`, byte-compatible |
| JVM: process, port 8095, thread pool, heap | one blast radius, one restart | three processes, three ports |
| Release train | any change redeploys all three | independent deploys |
| `PortalBrandingSettings` | a malformed host file fails startup for all three | not carried over; no host-file configuration |

## 4. Migration implications

- **Backfill is a straight copy** per table: `announcement`, `user_preference`, `feedback` move
  as-is. No transformation, no id remapping, no ordering constraint between the three moves,
  so the contexts can cut over independently and in any order.
- **Sequences must be carried.** `announcement.id` and `feedback.id` are identity columns; the
  new database's identity must resume above the highest migrated id or the first insert
  collides. `user_preference` has no sequence.
- **`created_at` is preserved verbatim.** It is the announcements list ordering and the
  feedback list ordering; regenerating it reorders live data.
- **H2 → PostgreSQL is the real risk**, not the split. The monolith runs H2 in memory by
  default with `ddl-auto: update`, so no reviewed DDL exists for production shapes. Each
  service therefore writes an explicit Flyway `V1` from the DDL in its contract and tests it on
  PostgreSQL via Testcontainers, not H2.
- **Two deliberate index additions** (`announcement (published, created_at DESC)`,
  `feedback (user_id, created_at DESC)`), both invisible on the wire and both covering a scan
  the assessment flagged. User preferences adds none — its only access is by primary key.
- **No dual-write and no sync.** Because nothing joins across contexts, the strangler cutover
  per context is: backfill, switch the route, keep the monolith endpoint deprecated for
  rollback. There is no window where two services must agree about the same row.
