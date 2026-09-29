# tkt01 — verify attempt 2 (on-sale reconciliation)

Branch `tkt/tkt01/integration` (head `c41f8a05` at run time, includes the verify-1 fixes: confirmations Kafka consumer,
payments outbox relay, VPC-CNI pod-IP capacity). Cluster EKS `otterworks-dev` / us-east-1. All data synthetic.
k6 run id **`20260929t053124`** (`load/run-onsale.sh tkt01`, defaults: RAMP=60s PEAK=600/min per side DURATION=120s
RAMPDOWN=30s MAX_VUS=300 PERFORMANCES=24 QUANTITY=2). Every request carried key `20260929t053124-<side>-<n>`.

## Verdict: all four shape checks PASS

| # | Shape check | Result | Numbers |
|---|-------------|--------|---------|
| 1 | Monolith (1 replica, 500m CPU) saturates at its CPU-allowed rate; p95 climbs past a few seconds | **PASS** | CPU used 0.4997 of 0.500 cores (Prometheus `max_over_time`, 1m rate); 201/min peaked at **261 orders/min** (ingress, 1m window) while k6 offered 600/min; k6 before p50 7 328 ms, **p95 33 449 ms**, p99 41 165 ms, max 45 637 ms; 1520 fired → 857 × 201, 92 × 500, 571 × 503 (monolith readiness flapped, `mono_ready` column in replicas-timeline.csv); ingress p95 pegged at the 10 s top bucket |
| 2 | Services sustain ~600 orders/min with p95 < 1000 ms, every service ≤ 6 replicas | **PASS** | 1649 fired → **1649 × 202** (0 errors); 202/min peaked at **603 orders/min** (ingress, 1m window), k6 offered 600/min; k6 after p50 45 ms, **p95 243 ms**, p99 3 076 ms, max 14 439 ms (cold start of orders from 0); max replicas: orders ksvc 6, payments 6, confirmations consumer 4, confirmations ksvc 3, seats ksvc 3, payments-relay 1, outbox-relay 1 — none above 6 |
| 3 | Payments consumer pod deleted mid-spike loses nothing (fired = placed = paid = confirmed on after) | **PASS** | `tkt01-payments-7765cc5b48-72lcs` deleted at **2026-09-29T05:33:11Z** with payments at 6/6; group `tkt01-payments` rebalanced (consumer-group-at-delete.txt), replacement `…-4l2m8` created 05:33:12Z; after: **1649 = 1649 = 1649 = 1649**, duplicates 0, missing 0, 0 payments-pod restarts, final lag 0 on all 6 partitions of both groups |
| 4 | Every service back at 0 replicas within 120 s after the spike | **PASS** | spike end 05:35:17Z → payments/payments-relay/confirmations-consumer 0 by 05:35:46Z (≤29 s; payments Deployment 1→0 event 05:35:42Z = 25 s), outbox-relay 0 by 05:36:11Z (≤54 s), orders ksvc and confirmations ksvc 0 by **05:36:36Z (≤79 s)**. seats ksvc stays at 1 by design (per-minute hold-sweep CronJob) |

## Reconciliation (databases + k6 summary), run `20260929t053124`

| namespace | fired (k6) | placed / accepted | paid (CAPTURED) | confirmed / settled | duplicates (payments per order > 1) | missing (accepted but not paid) |
|-----------|-----------:|------------------:|----------------:|--------------------:|------------------------------------:|--------------------------------:|
| tkt01-before | 1520 | 857 (201) | 857 | 857 (CONFIRMED, 1714 tickets) | 0 | 0 |
| tkt01-after  | 1649 | 1649 (202) | 1649 | 1649 (CONFIRMED, 3298 tickets, 3298 seats SOLD) | 0 | 0 |

The after side reads the same number in every column. Before-side rejects (92 × 500 + 571 × 503 = 663) never created an
order, so they are neither placed nor missing. k6 reported 129 dropped iterations on the before scenario (the 600/min
arrival-rate executor ran out of VUs while the monolith queued requests for 30–45 s).

After-side detail (reconciliation.json, queried 05:36:45Z, ~90 s after spike end; identical on re-check at 05:43Z):

- orders: 1649 rows `client_ref like '20260929t053124-after-%'`, status CONFIRMED 1649, payment_outcome APPROVED 1649,
  3298 order items ticketed, outbox 1649 rows / 0 unpublished
- payments: 1649 rows, CAPTURED 1649, 1649 attempts (no order with >1 attempt), duplicate_deliveries suppressed 0,
  outcome_deliveries CONFIRMATIONS:delivered 1649 / pending 0 / given_up 0
- confirmations: 1649 confirmations (delivered_at set on all 1649), 3298 tickets
- seats: 3298 seat_inventory SOLD, 1649 holds CONVERTED, inbox order-confirmed 1649
- Kafka: `tkt01-payments` and `tkt01-confirmations` groups lag 0 on all 6 partitions (consumer-groups-final.txt;
  log-end 288/278/244/273/303/263 = 1649)

Before-side detail: 857 orders (`customers.email like 'k6-20260929t053124-before-%'`), 857 payments CAPTURED,
857 confirmations, 1714 tickets, 0 orders with >1 payment row.

Note on check 3: because payments commits the source offset after the DB transaction and the Kafka publish, the
deleted pod's partitions were resumed from the committed offsets and no record needed the idempotency key
(duplicate_deliveries_suppressed = 0). The group described 8 s after the delete had all six partitions on one surviving
consumer while the rebalance settled (consumer-group-at-delete.txt); lag peaked at 368 during the payments cold start
at 05:32:28Z and was 10 → 0 by 05:34:38Z.

## Timeline (UTC, 2026-09-29) — timestamps.txt

| event | time |
|-------|------|
| reset.sh start | 05:03:03Z |
| reset.sh exit 1 (deploy.sh step 6/6 certificate wait; see infrastructure note) | 05:17:04Z |
| deploy.sh remaining readiness probes + load/seed.sh run by hand | 05:18:31Z – 05:20:29Z |
| at-rest status recorded (at-rest-status.txt) | 05:23:26Z |
| run-onsale.sh start (first attempt at 05:25Z aborted before creating the Job — no requests fired) | 05:31:21Z |
| k6 Job `tkt01-onsale-20260929t053124` running | 05:31:40Z |
| payments Deployment 0 → 1 → 6 | 05:32:25Z → 05:32:32Z |
| **payments pod `tkt01-payments-7765cc5b48-72lcs` deleted** | **05:33:11Z** |
| k6 finished (spike end) | **05:35:17Z** |
| first sample after spike end with lag 0 / outbox 0 / deliveries 0 (drain) | 05:35:20Z (**≤3 s**; already 0 at 05:34:38Z during rampdown) |
| payments Deployment 1 → 0 (ReplicaSet event) | 05:35:42Z (25 s) |
| orders + confirmations ksvc at 0 pods — every service except seats at 0 | **05:36:36Z (79 s)** |
| final status (final-status.txt) — both namespaces left running | 05:43:36Z |

At rest before the run (at-rest-status.txt): tkt01-before `tkt01-db 1/1`, `tkt01-monolith 1/1` (2 pods); tkt01-after
orders ksvc 0, confirmations ksvc 0, confirmations-consumer 0/0, payments 0/0, payments-relay 0/0, orders-outbox-relay 0/0
(all ScaledObjects READY, ACTIVE=False), seats ksvc 1/1, four service DBs 1/1, kafka broker 1, entity-operator 1,
kafka-exporter 1 (8 pods). Identical after the run (final-status.txt).

## Measurements

| measurement | value |
|-------------|-------|
| monolith_saturation_rpm | 261 (max 1m-window 201/min; monolith CPU 0.4997/0.500 cores) |
| services_peak_rpm | 603 (max 1m-window 202/min; 1649 accepted of 1649) |
| services_p95_ms | 243 (k6, whole run; ingress 1m-window p95 peaked at 2 293 ms during the 05:32 cold start) |
| max_replicas_seen | 6 (orders ksvc and payments) |
| pod_deleted_at | 2026-09-29T05:33:11Z (`tkt01-payments-7765cc5b48-72lcs`) |
| drain_seconds | 3 (first sample after spike end; backlogs already 0 during rampdown) |
| scale_to_zero_seconds | 79 (orders/confirmations ksvc; payments 25 s; seats intentionally stays at 1) |

## Infrastructure note (not a shape-check failure)

`reset.sh tkt01` exited 1 at 05:17:04Z: `deploy/after/deploy.sh` step 6/6 waits for the per-token
`certificate/tkt01-after-tls`, and Let's Encrypt refused the order with
`429 rateLimited: too many certificates (5) already issued for this exact set of identifiers in the last 168h,
retry after 2026-09-30 12:14:38 UTC` (five resets of the same token hosts this week). Both hosts were nevertheless
served with a valid certificate — ingress-nginx's default `*.demo.otterworks.app` wildcard (`ingress-nginx/otterworks-wildcard-tls`,
curl `ssl_verify_result=0`) — so the remaining deploy.sh readiness probes and `load/seed.sh tkt01` were run by hand
(seed.log: availability parity on performances 1/7/13/24, before stats zeroed). Suggested integration follow-up: make the
per-token certificate wait non-fatal when the default wildcard already covers the host (or drop the per-token
Certificate and rely on the wildcard), otherwise a reset cannot complete more than 5× per week per token.

## Captures (Grafana `ticketing-onsale-tkt01`, 05:20–05:40Z, kiosk)

- dashboard-full.png — both rows (Before — monolith / After — services)
- panel-02-before-request-rate.png, panel-03-before-latency.png, panel-04-before-errors.png,
  panel-05-before-cpu-vs-limit.png, panel-06-before-replicas.png
- panel-08-after-request-rate.png, panel-09-after-latency-p95.png, panel-10-after-errors.png,
  panel-11-after-replicas.png, panel-12-after-kafka-lag.png, panel-13-after-outbox-backlog.png,
  panel-14-after-payments-restarts-outcomes.png, panel-15-after-pods-not-ready.png

## Files

k6-summary.json (= .runs/tkt01/onsale-20260929t053124.json), k6-onsale.log, onsale.log, reconciliation.json,
replicas-timeline.csv (≈25 s poll of replicas / Kafka lag / outbox / outcome-delivery backlog / non-ready pods),
drain-watch.txt, consumer-group-at-delete.txt, consumer-groups-final.txt, payments-pods-before-delete.txt,
at-rest-status.txt, final-status.txt, reset.log, seed.log, timestamps.txt.
