# tkt01 — VERIFY attempt 1 (on-sale, both namespaces at once)

Branch `tkt/tkt01/integration` @ `f318c9dc`. Run id `verify1t040736`. k6 shape (defaults of
`ticketing/load/run-onsale.sh`): RAMP=60s → PEAK=600 orders/min for DURATION=120s → RAMPDOWN=30s, MAX_VUS=300,
PERFORMANCES=24, QUANTITY=2, both sides fired concurrently through the shared ingress-nginx.

**Overall: FAIL** (2 of 4 shape checks failed). The load, saturation and scale-out shapes are as designed, but the
after side lost 1643 of 1649 orders to hold expiry because `confirmations` could not be scheduled for ~10 minutes
(cluster nodes that cannot assign pod IPs) and `payments` blocks its partitions on the synchronous HTTP inbox
delivery to confirmations. Scale-to-zero was consequently 676 s instead of ≤120 s. Details and findings below.

## Timeline (UTC, 2026-09-29)

| time | event |
|---|---|
| 03:56:51 | `scripts/reset.sh tkt01` start (transcript: `reset.log`) |
| 04:04:44 | reset complete: both namespaces rebuilt from seed |
| 04:07:18 | at-rest replicas recorded (`at-rest-status.txt`): before `tkt01-db 1/1`, `tkt01-monolith 1/1`; after `orders 0`, `confirmations 0`, `payments 0/0` (KEDA ACTIVE=False), `orders-outbox-relay 0/0` (KEDA ACTIVE=False), `seats 1/1` (kept warm by the per-minute hold-sweep CronJob), 4 DBs 1/1, kafka broker/entity-operator/exporter 1 each |
| 04:07:36 | `load/run-onsale.sh tkt01` launched (k6 job `tkt01-onsale-verify1t040736`) |
| 04:08:03 | first orders land; outbox backlog peaks at 119 unpublished rows (relay cold start), 4 by 04:08:30 |
| 04:08:30 | payments 0 → 1 (KEDA activation) |
| 04:08:38 | payments desired 6/6 (max); orders ksvc 1, confirmations ksvc 0 → 1 requested |
| 04:08:50 (approx) | Karpenter adds spot node `ip-10-0-100-116` (tenants pool, us-east-1a); confirmations pod + 2 payments pods scheduled there stay `ContainerCreating` (`FailedCreatePodSandBox: aws-cni failed to assign an IP address`) |
| **04:09:18** | **`kubectl delete pod tkt01-payments-6557d88f48-6jcz6`** (a Ready consumer; 5 of 6 payments pods Ready at the time); replacement `…-w5cbr` lands on the bad node and never starts |
| 04:09:00–04:11:30 | monolith pinned at 498–499 millicores (limit 500m); ingress p95 for before ≥ 10 s (bucket ceiling), 503/500 spill |
| 04:11:35.6 | k6 `finished_at`; job Complete 04:11:38 — **spike end used below: 04:11:38** |
| 04:12:13 | orders-outbox-relay back to 0 (outbox unpublished = 0 since 04:11:27) |
| 04:12:08 | consumer group `tkt01-payments`: CURRENT-OFFSET 0 on all 6 partitions, lag 1649 — payments captured 6 payments and is stuck retrying the inbox POST to confirmations (`Request timed out`, `Record in retry and not yet recovered`) |
| 04:13:38 | remediation: cordoned `ip-10-0-100-116`, deleted the stuck pods; confirmations + payments reschedule on healthy nodes |
| 04:16:23 | confirmations now reachable but its own downstream call to seats times out: seats pod had been rescheduled onto a second fresh node `ip-10-0-100-115` with the same CNI failure |
| 04:17:17 | remediation: cordoned `ip-10-0-100-115`, deleted stuck pods; seats lands on a third fresh node `ip-10-0-100-33`, same failure |
| 04:20:25 | remediation: cordoned `ip-10-0-100-33`, deleted stuck pods; seats schedules on `ip-10-0-101-131` (us-east-1b) and is Ready 04:20:30 |
| 04:21:14 | lag 548 and falling (payments now committing offsets) |
| **04:21:40** | **Kafka consumer lag 0, outbox unpublished 0 — drain complete** |
| 04:22:34 | payments 0/0 (KEDA cooldown) |
| 04:22:25 / 04:22:54 | confirmations 0 / orders 0 (Knative) |
| 04:23:38 | seats back to 1 (its at-rest state; never 0 by design) |

## Reconciliation (databases + k6 summary)

k6 summary: `k6-summary.json` (also ConfigMap `tkt01-after/tkt01-onsale-summary`). DB queries: `reconciliation.json`
(before: `orders`/`payments`/`tickets` joined through customers with email `k6-verify1t040736-before-*`; after:
`orders.client_ref like 'verify1t040736-after-%'`, payments/confirmations/seats joined on `order_ref`).

| namespace | fired | accepted (201/202) | placed (orders rows) | paid (CAPTURED, distinct orders) | confirmed / settled | duplicates (payments per order > 1) | missing (accepted, not paid) |
|---|---|---|---|---|---|---|---|
| tkt01-before | 1538 | 821 | 821 | 821 | 821 (1642 tickets) | 0 | 0 |
| tkt01-after | 1649 | 1649 | 1649 | **6** | **6** (6 settled confirmations, 12 tickets) | 0 | **1643** |

After-side detail: `orders.status` = {CONFIRMED: 6, CANCELLED: 1643}; `orders.payment_outcome` = {APPROVED: 6,
HOLD_EXPIRED: 1643}; `payments.status` = {CAPTURED: 6, EXPIRED: 1643}; `outbox_total` = 1649, `outbox_unpublished` = 0;
`seats_sold` = 0, `holds_converted` = 0 (holds lapsed and were swept). Every after-side column is *not* the same
number: fired = accepted = placed = 1649 ≠ paid = confirmed = 6.

Before-side detail: k6 fired 1538, statuses {201: 821, 500: 120, 503: 597}; the 717 rejected requests created no
orders (821 orders = 821 payments = 821 confirmations), so the monolith lost nothing it accepted — it simply refused
~47 % of the offered load.

Idempotency evidence (after): `payments.duplicate_deliveries` sum = 225 across 6 rows (max 43 on one order) — every
redelivered `order-placed` record was suppressed by the unique key on `order_ref`; `duplicates` = 0 and
`orders_with_multiple_attempts` = 0.

## Shape checks

### 1. Monolith saturates at its CPU-allowed rate; p95 climbs past a few seconds — **PASS**
- Monolith CPU (Prometheus, 1-min rate): 286 m at 04:08:30, then 498–499 m from 04:09:00 to 04:11:30 against a 500 m limit.
- Accepted rate (ingress `201`/min, 30 s samples): 113, 206, 203, **237**, 234, 234, 229, 123 → plateau ≈ 230–237 orders/min while offered load ramped to 600/min. **monolith_saturation_rpm = 237** (peak 1-min 201 rate).
- Excess turned into 500 (peak 47/min) and 503 (peak 333/min; the readiness probe failed under saturation, so ingress-nginx returned 503).
- Latency: ingress p95 for before = 4.4 s at 04:08:30 and ≥ 10 s (histogram ceiling) from 04:09:00; k6 client p50 3.9 s, p95 **30.8 s**, p99 38.9 s, max 47.3 s.

### 2. Services sustain ~600 orders/min with p95 < 1000 ms, no service above 6 replicas — **PASS (at the API; see check 3 for settlement)**
- Ingress `202`/min on `tkt01-after` peaked at **599 orders/min** (k6 target 600; fired 1649 in 228 s, 0 non-202). **services_peak_rpm = 599**.
- Latency: k6 p50 29 ms, p95 **51 ms**, p99 63 ms, max 9.66 s (one cold-start outlier); ingress-side 1-min p95 91–92 ms during the ramp (orders cold start), 48 ms at peak. **services_p95_ms = 51** (k6; 92 ms worst ingress 1-min p95).
- Max replicas in the window (`kube_deployment_status_replicas`): orders 6, payments 6, seats 5, confirmations 1, outbox-relay 1 → **max_replicas_seen = 6**, none above 6.
- Caveat: 599 rpm is ≈ 2.5× the monolith's *accepted* plateau (237 rpm), not 10×; the 10× wording holds only against the monolith's degraded-latency envelope (the monolith still served 237 rpm, at p95 > 10 s). Kept as PASS against the literal thresholds (600 rpm, p95 < 1000 ms, ≤ 6 replicas).

### 3. Payments pod deleted mid-spike loses nothing; fired = placed = paid = confirmed on the after side — **FAIL**
- Deleted `tkt01-payments-6557d88f48-6jcz6` at **04:09:18Z** while payments was at 6 desired / 5 ready. Its partitions were reassigned (consumer group described at 04:12:08 shows 4 consumers holding all 6 partitions) and redelivery was a no-op (225 suppressed duplicates, 0 duplicate payments). *The pod kill itself lost nothing.*
- But paid = confirmed = 6 ≠ fired = placed = 1649. Cause chain (`consumer-groups-041208.txt`, `stuck-pods-on-bad-node.txt`, payments/confirmations logs):
  1. Knative scaled confirmations 0 → 1 at 04:08:38; the pod (and 2 of 6 payments pods, incl. the replacement for the killed one) were scheduled on a Karpenter spot node whose aws-cni could not assign pod IPs, so they never started.
  2. `payments` captures the payment, then delivers the outcome to Kafka **and** synchronously POSTs it to the confirmations HTTP inbox; the POST timed out and the `DefaultErrorHandler(FixedBackOff(2000, UNLIMITED))` retried the same record forever, so no offset was ever committed (CURRENT-OFFSET 0 on all partitions, lag 1649 at 04:12:08) and the whole partition stalled behind one record.
  3. Holds are 10 minutes; by the time confirmations/seats were schedulable (after cordoning three consecutive bad nodes, 04:13–04:20) `holdExpiresAt` was in the past for 1643 orders, so payments recorded them EXPIRED (no gateway call) and orders were CANCELLED/HOLD_EXPIRED.
- **drain_seconds = 602** (spike end 04:11:38 → lag 0 and outbox 0 at 04:21:40); outbox alone was 0 by 04:11:27.

### 4. Every service back at 0 replicas within 120 s after the spike — **FAIL**
- From spike end 04:11:38: outbox-relay 0 at 04:12:13 (**35 s**, OK); payments 0 at 04:22:34 (**656 s**); confirmations 0 at 04:22:25 (647 s); orders 0 at 04:22:54 (**676 s**). **scale_to_zero_seconds = 676** (all services except seats).
- Seats settled back to its at-rest 1 replica at 04:23:38 (expected; the hold-sweep CronJob keeps it warm).
- Direct consequence of check 3: payments could not commit offsets, so KEDA lag stayed at 1649 and the consumers stayed at 6 for 10 minutes; orders and confirmations then spiked again (orders 6, seats 5) at 04:21:46 when the backlog finally drained.

## Measurements

| key | value |
|---|---|
| monolith_saturation_rpm | 237 (plateau 229–237, CPU 498–499 m / 500 m) |
| services_peak_rpm | 599 |
| services_p95_ms | 51 (k6 client); 92 ms worst ingress 1-min p95 |
| max_replicas_seen | 6 (orders 6, payments 6, seats 5, confirmations 1, relay 1) |
| pod_deleted_at | 2026-09-29T04:09:18Z (`tkt01-payments-6557d88f48-6jcz6`) |
| drain_seconds | 602 |
| scale_to_zero_seconds | 676 (payments 656, confirmations 647, orders 676, relay 35; seats stays at 1 by design) |

## Findings

1. **integration** — Karpenter `tenants` spot nodes in us-east-1a (`ip-10-0-100-116`, `-115`, `-33`, all created during the run) fail `FailedCreatePodSandBox: aws-cni failed to assign an IP address`; every tkt01 pod scheduled on them sat in ContainerCreating (also kube-system `ebs-csi-node`, platform CronJobs). Subnet `10.0.100.0/24` reported 66 free IPs, so this looks like a per-node ENI/prefix allocation problem rather than exhaustion. Suggested fix: fix the CNI on that node class (prefix delegation / ENI limits / node role permissions) or exclude the pool for `tkt*-after` workloads with a nodeSelector/taint, and add a `KubePodNotReady`/`FailedCreatePodSandBox` alert; until then keep the three nodes cordoned (they are).
2. **payments** — `OutcomePublisher` delivers `payment-captured` to Kafka *and* synchronously to the confirmations HTTP inbox and requires both to succeed; with `FixedBackOff(2000, UNLIMITED_ATTEMPTS)` one unreachable inbox blocks the partition indefinitely and no offset is committed (lag 1649 for 10 min, replicas pinned at 6). Suggested fix: make the HTTP inbox delivery best-effort (bounded retries, then rely on the Kafka record) or move it to an outbox table with its own relay, so the consumer commits after the DB transaction + Kafka send as the convention says.
3. **confirmations** — the only trigger for a confirmation is the HTTP inbox POST; it does not consume `tkt01-payment-captured`, so when the pod is unschedulable the captured events pile up on the producer instead of in the topic. Suggested fix: consume `payment-captured` from Kafka (idempotent on `order_ref`) and treat the inbox as an accelerator; optionally `min-scale: 1` for the on-sale window.
4. **integration** — scale-to-zero took 676 s (> 120 s) as a consequence of 1–2; no separate scaling defect was observed (relay 35 s; KEDA/Knative scale-down happened within ~60–75 s once lag hit 0). Fix 1–2 and re-run. Also: the Strimzi Kafka exporter exposes no `kafka_consumergroup_lag` series until the group has committed an offset, so the Grafana lag panel only shows KEDA's own metric during a fresh-cluster run.

## Captures (Grafana `ticketing-onsale-tkt01`, 04:06–04:25 UTC)

`dashboard-full.png` (both rows), `panel-02-request-rate-shared-ingress-monolith.png`, `panel-03-latency-p50-p95.png`,
`panel-04-errors.png`, `panel-05-cpu-used-vs-limit.png`, `panel-06-replicas.png`,
`panel-08-request-rate-by-service-shared-ingress-kourier-knative.png`, `panel-09-latency-p95-per-service.png`,
`panel-10-errors-by-service.png`, `panel-11-replicas-per-service-0-6.png`,
`panel-12-kafka-consumer-lag-order-placed-payments.png`, `panel-13-outbox-backlog-orders-order-placed.png`,
`panel-14-payments-pod-restarts-outcomes.png`.

Other evidence in this directory: `k6-summary.json`, `k6-onsale.log`, `reconciliation.json`, `prometheus-run-window.json`,
`replicas-timeline.csv` (9 s poll of replicas / pods / outbox), `drain-watch.txt`, `scale-to-zero-watch.txt`,
`consumer-groups-041208.txt`, `consumer-group-final.txt`, `stuck-pods-on-bad-node.txt`, `at-rest-status.txt`,
`post-run-status.txt`, `timestamps.txt`, `reset.log`.

Both namespaces (`tkt01-before`, `tkt01-after`) were left running; nodes `ip-10-0-100-116/-115/-33` remain cordoned.
