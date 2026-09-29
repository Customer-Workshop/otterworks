# Ticketing modernization demo — presenter runbook (run token `tkt01`)

For a presenter who was not in the loop. Everything here is synthetic (invented promoters, venues, customers and
card numbers). Every timing below was measured on this cluster during run `tkt01`; nothing is estimated.

**What the audience sees:** a Jakarta EE ticketing monolith (`ticketing/monolith/`, 1 replica, 500 millicores)
and the first extracted slice (`orders`, `seats`, `payments`, `confirmations` as Knative / KEDA services behind
Kafka) take the same on-sale spike at the same time through the same ingress. The monolith saturates at about
261 orders/min with a p95 of 33 s; the services take 603 orders/min at a p95 of 243 ms, survive a payments pod
being killed mid-spike without losing an order, and are back at zero replicas 79 s after the spike ends.

| | |
|---|---|
| Branch | `tkt/tkt01/integration` (PR into `review-base-ticketing`; never `main`) |
| PR | https://github.com/Cognition-Partner-Workshops/otterworks/pull/1738 |
| Hosts | `https://tkt01-before.demo.otterworks.app` (monolith), `https://tkt01-after.demo.otterworks.app` (services) |
| Grafana | `https://grafana.otterworks.app/d/ticketing-onsale-tkt01` (dashboard "Ticketing on-sale — before vs after") |
| Cluster | EKS `otterworks-dev`, us-east-1; namespaces `tkt01-before` and `tkt01-after` |
| Evidence of the verified run | `ticketing/evidence/tkt01/verify-2/` (report: `reconciliation.md`) |

---

## 1. Preflight (the day before, and again 30 min before)

Run from a checkout of `tkt/tkt01/integration` in the repo root.

```bash
# 1. Credentials + cluster (if the default identity is refused, export the AWS_DEMO_* pair as AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY)
aws sts get-caller-identity
aws eks update-kubeconfig --name otterworks-dev --region us-east-1
kubectl get crd services.serving.knative.dev scaledobjects.keda.sh kafkas.kafka.strimzi.io   # platform present

# 2. Both namespaces at rest (expected output in §3)
make ticketing-status NS=tkt01

# 3. Both hosts answer through the shared ingress
curl -s https://tkt01-before.demo.otterworks.app/api/health           # {"status":"UP"}
curl -s https://tkt01-after.demo.otterworks.app/api/stats | jq .ordersTotal   # a number (first call cold-starts orders from 0; the slowest cold-start request measured was 14.4 s)
curl -s https://tkt01-after.demo.otterworks.app/api/performances/1/availability | jq .   # seats

# 4. One real purchase on each side, end to end (before → 201 CONFIRMED; after → 202 then CONFIRMED)
ticketing/scripts/smoke.sh tkt01
```

Then open, in separate browser tabs, in this order (it is the order you present them):

1. The workflow run — the orchestrator session
   <https://partner-workshops.devinenterprise.com/sessions/cc9e6c3bc8ae4ced9ed05049c8ab0097> (its run view lists
   every stage as a child session; the direct links are in §7).
2. The decomposition note `ticketing/docs/decomposition.md` at §2.2 ("The single JTA transaction in
   `PurchaseFacadeBean`") and §4.1 ("Target flow (after)"), next to the bean it came from:
   `ticketing/monolith/src/main/java/com/boxoffice/sales/PurchaseFacadeBean.java` lines 54–71 (`completeHold`,
   six contexts in one transaction). The note pins every link to base commit `cb628c9f`.
3. Grafana `https://grafana.otterworks.app/d/ticketing-onsale-tkt01?from=now-15m&to=now&refresh=10s` — two rows,
   "Before — monolith" and "After — services". Confirm the row "Replicas per service (0 → 6)" shows everything at 0
   except seats at 1.
4. The reconciliation report of the verified run: `ticketing/evidence/tkt01/verify-2/reconciliation.md`.
5. The PR from `tkt/tkt01/integration` into `review-base-ticketing` and its Devin Review comment (§7).

Also check `make ticketing-status NS=tkt01` prints "pod IP capacity" with a non-zero number of free /28 blocks in
both AZs. Verify attempt 1 lost 10 minutes to nodes that could not assign pod IPs; the deploy scripts now refuse to
start in an AZ with none.

If anything in step 2 or 3 is wrong, do the reset in §2 now, not during the talk.

---

## 2. The one reset command

```bash
make ticketing-reset NS=tkt01         # → ticketing/scripts/reset.sh tkt01
```

It deletes both namespaces, redeploys the monolith and the four services + Kafka, re-seeds both sides from the same
deterministic seed, compares seat availability on the two hosts, and finishes by printing `make ticketing-status`.

Measured wall-clock time, start to "reset complete":

| run | time |
|---|---|
| integration stage | **437 s** |
| verify attempt 1 (`evidence/tkt01/verify-1/reset.log`) | **460 s** (03:56:51Z → 04:04:31Z) |
| verify attempt 2 | exited 1 after 841 s — see the certificate note below; seeding by hand took 103 s |

**Budget 8 minutes, and never start it less than 15 minutes before you need the cluster.** It writes a transcript
to `ticketing/.runs/tkt01/`.

**Known failure: Let's Encrypt rate limit.** `deploy/after/deploy.sh` step 6/6 waits up to 8 minutes for the
per-token certificate `tkt01-after-tls`. Let's Encrypt allows 5 certificates per exact host set per 168 h; the
sixth reset in a week gets `429 rateLimited` and `reset.sh` exits 1 *after* both namespaces are deployed but
*before* the seed step. Both hosts are still served with a valid certificate by ingress-nginx's default
`*.demo.otterworks.app` wildcard, so the demo is unaffected. Finish by hand (measured 103 s on 2026-09-29):

```bash
ticketing/load/seed.sh tkt01
make ticketing-status NS=tkt01
```

The verify-2 report records when the limit clears (2026-09-30 12:14Z for this host set). A `reset.sh` that goes
quiet on "6/6 waiting for the certificate" is this problem.

---

## 3. Replica counts at rest (expected `make ticketing-status NS=tkt01`)

Recorded before and after the verified run (`verify-2/at-rest-status.txt`, `final-status.txt`) — identical.

| namespace | object | desired / ready | note |
|---|---|---|---|
| `tkt01-before` | `tkt01-monolith` Deployment | 1 / 1 | WildFly, CPU limit 500m, `PRICING_PASSES=200` |
| `tkt01-before` | `tkt01-db` Deployment | 1 / 1 | postgres:16-alpine, emptyDir |
| `tkt01-after` | `tkt01-orders` Knative Service | **0** | scales 0 → 6 on requests per second |
| `tkt01-after` | `tkt01-confirmations` Knative Service | **0** | 0 → 6 |
| `tkt01-after` | `tkt01-seats` Knative Service | **1** / 1 | kept warm on purpose by its per-minute hold-sweep CronJob |
| `tkt01-after` | `tkt01-payments` Deployment (KEDA, Kafka lag) | **0 / 0**, ScaledObject READY, ACTIVE=False | 0 → 6 |
| `tkt01-after` | `tkt01-payments-relay` Deployment (KEDA) | 0 / 0 | max 2 |
| `tkt01-after` | `tkt01-orders-outbox-relay` Deployment (KEDA) | 0 / 0 | max 1 |
| `tkt01-after` | `tkt01-confirmations-consumer` Deployment (KEDA) | 0 / 0 | max 6 |
| `tkt01-after` | `tkt01-orders-db`, `-seats-db`, `-payments-db`, `-confirmations-db` | 1 / 1 each | one database per service |
| `tkt01-after` | Kafka: broker 1, entity-operator 1, kafka-exporter 1 | 1 each | Strimzi, KRaft, ephemeral |

Running pods: **2** in `tkt01-before`, **8** in `tkt01-after`. Anything else at rest means the cluster is not
idle — wait two minutes (KEDA cooldown) and re-run status before deciding to reset.

---

## 4. Live steps (the spike itself ran 3 min 37 s, k6 start to finish, in the verified run)

The verified run used the defaults of `ticketing/load/run-onsale.sh`: 60 s ramp to **600 orders/min per side**,
120 s hold, 30 s ramp-down, both hosts hit concurrently by one in-cluster k6 Job through the shared ingress. Every
request is tagged with a run id (`<run_id>-<side>-<n>`), which is what makes the reconciliation exact.

### 4.1 Frame it (tabs 1 and 2)

- Workflow run view: point at the stage list — assess (1), build (4 concurrent), integrate, verify ⇄ fix (2 fix
  rounds used), ship. Each is a separate Devin session; the links are in §7.
- Decomposition note beside `PurchaseFacadeBean.completeHold` (lines 54–71): six contexts chained inside one JTA
  transaction (`customers → holds → pricing → orders → payments → confirmations`); §2.1 gives each of the 30 tables
  one owner; §4.1 is the event flow the slice implements (`order-placed → payments → payment-captured →
  confirmations → order-confirmed`). Table ownership and event payloads in the note were the contract the four
  build sessions coded against.

### 4.2 Show the at-rest state (tab 3 + terminal)

`make ticketing-status NS=tkt01` and the Grafana row "After — services": every service at 0 except seats.

### 4.3 Fire the on-sale

```bash
ticketing/load/run-onsale.sh tkt01            # streams the k6 log; returns when the job completes (3 min 37 s in the verified run)
```

Measured timeline of the verified run (UTC, 2026-09-29), relative to the k6 Job starting (05:31:40Z):

| +time | what you see |
|---|---|
| 0 s | k6 running; both request-rate panels start climbing |
| first requests | orders Knative Service cold-starts from 0 (the ingress 1-min p95 for "after" spiked once to 2 293 ms during 05:32, then fell; the slowest single request of the run was 14 439 ms) |
| +45 s | payments 0 → 1 (KEDA sees lag on `tkt01-order-placed`), 6/6 seven seconds later |
| +60 s | 600/min per side reached. Monolith CPU panel pins at the 0.5-core limit; its p95 climbs past 10 s (the top histogram bucket); 503s and 500s appear. Services: 202/min tracks the offered rate (k6 p95 243 ms over the whole run) |
| **+91 s** | **you delete a payments pod (4.4)** |
| +180 s (scripted: 60 s ramp + 120 s hold) | hold ends, 30 s ramp-down |
| +217 s | k6 finished ("spike end" 05:35:17Z); the script prints fired/accepted/p95 per side |

Numbers to say out loud (from the verified run): monolith accepted **857** of 1520 fired (**92 × 500, 571 × 503**),
peaked at **261 orders/min**, k6 p95 **33 449 ms**; services accepted **1649 of 1649** (all 202), peaked at
**603 orders/min**, k6 p95 **243 ms**, max **6** replicas (orders and payments).

### 4.4 Kill a payments consumer mid-spike (at about +90 s, once payments shows 6/6)

```bash
kubectl -n tkt01-after get pods -l app.kubernetes.io/name=payments -o wide     # six Running pods
kubectl -n tkt01-after delete pod <one of them>                                  # verified run: tkt01-payments-7765cc5b48-72lcs at 05:33:11Z
kubectl -n tkt01-after get deploy tkt01-payments -w                             # replacement pod within 1 s; 6/6 again shortly after
```

What to point at: Grafana "Payments pod restarts & outcomes" (pods running dips 6 → 5 → 6; restarts stay 0 — it is a
new pod, not a restart) and "Kafka consumer lag (order-placed → payments)" (a small bump while the group rebalances;
verified run: the consumer group was on one surviving member 8 s after the delete, lag back to 0 by 05:34:38Z).
Why nothing is lost: payments commits its Kafka offset only after the DB transaction and the outbound publish, and
the order reference is a unique key, so a replayed record is a no-op.

### 4.5 Drain and scale to zero (the 2 minutes after k6 finishes)

Watch "Kafka consumer lag", "Outbox backlog" and "Replicas per service" together, or in a terminal:

```bash
kubectl -n tkt01-after get scaledobject                       # ACTIVE flips True → False
kubectl -n tkt01-after get deploy,ksvc -w
```

Measured after the verified spike end (05:35:17Z):

| event | measured |
|---|---|
| Kafka lag 0, outbox 0, pending deliveries 0 (drained) | **≤ 3 s** (backlogs were already 0 during the ramp-down) |
| payments Deployment 6 → … → 0 | **25 s** (payments, payments-relay and confirmations-consumer all at 0 by 29 s) |
| orders-outbox-relay 0 | 54 s |
| orders and confirmations Knative Services at 0 — everything except seats | **79 s** |

The shape requirement was 120 s. Seats stays at 1 by design (its hold-sweep CronJob calls it every minute).

### 4.6 Reconcile (fired = placed = paid = confirmed)

Live, right after the drain:

```bash
RUN=$(jq -r .run_id ticketing/.runs/tkt01/onsale-latest.json)
jq '.sides' ticketing/.runs/tkt01/onsale-latest.json                          # fired / accepted / statuses / p95 per side (k6)
curl -s https://tkt01-after.demo.otterworks.app/api/stats | jq '{ordersTotal, ordersByStatus, ticketsStamped, outboxUnpublished}'
curl -s https://tkt01-before.demo.otterworks.app/api/stats | jq .
```

On the after side `accepted` (k6) must equal `ordersByStatus.CONFIRMED` and `outboxUnpublished` must be 0. Then
open the committed report for the verified run, `ticketing/evidence/tkt01/verify-2/reconciliation.md`: after side
**1649 fired = 1649 accepted = 1649 paid CAPTURED = 1649 CONFIRMED**, 0 duplicates, 0 missing, 0 unpublished outbox
rows, both consumer groups at lag 0; before side 857 = 857 = 857 = 857 with 663 rejected at the door.

### 4.7 Close on the PR (tab 5)

The single PR, https://github.com/Cognition-Partner-Workshops/otterworks/pull/1738, from `tkt/tkt01/integration` into `review-base-ticketing`: the four services, the deploy and load
scripts, the dashboard, the decomposition note, the two reconciliation reports and this runbook. Scroll to the
Devin Review comment and read its findings as they stand — nothing was pushed to silence them. Do not merge.

---

## 5. Where each metric lives

| measurement (verified value) | Grafana panel (dashboard `ticketing-onsale-tkt01`) | source query / file |
|---|---|---|
| Monolith request rate by status; saturation **261 orders/min** | Before → "Request rate (shared ingress → monolith)" | `sum by (status) (rate(nginx_ingress_controller_requests{exported_namespace="tkt01-before"}[1m]))` |
| Monolith p50 / p95 (**p95 33 449 ms**, k6) | Before → "Latency p50 / p95" | `nginx_ingress_controller_request_duration_seconds_bucket{exported_namespace="tkt01-before"}`; k6 numbers in `verify-2/k6-summary.json` |
| Monolith 5xx / 4xx (**92 × 500, 571 × 503**) | Before → "Errors" | same ingress counter, `status=~"5.."` |
| Monolith CPU (**0.4997 of 0.500 cores**) | Before → "CPU used vs limit" | `rate(container_cpu_usage_seconds_total{namespace="tkt01-before",container="wildfly"}[1m])` vs `kube_pod_container_resource_limits` |
| Monolith replicas (1) | Before → "Replicas" | `kube_deployment_status_replicas_available{namespace="tkt01-before"}` |
| Services request rate per path (**603 orders/min**) | After → "Request rate by service (shared ingress → Kourier → Knative)" | `sum by (ingress) (rate(nginx_ingress_controller_requests{exported_namespace="tkt01-after"}[1m]))` |
| Services p95 per service (**k6 p95 243 ms**; ingress 1-min p95 peaked 2 293 ms on the cold start) | After → "Latency p95 per service" | ingress histogram, `exported_namespace="tkt01-after"` |
| Services errors (**0**) | After → "Errors by service" | ingress counter, `status=~"5.."` |
| Replicas per service (**max 6**, orders and payments) | After → "Replicas per service (0 → 6)" | `kube_deployment_status_replicas_available` for `tkt01-orders-*-deployment`, `tkt01-payments`, … ; `verify-2/replicas-timeline.csv` (25 s polls) |
| Kafka consumer lag (drain **≤ 3 s**) | After → "Kafka consumer lag (order-placed → payments)" | `kafka_consumergroup_lag{namespace="tkt01-after"}` (kafka-exporter) and `keda_scaler_metrics_value{scaledObject="tkt01-payments"}`; `verify-2/drain-watch.txt`, `consumer-groups-final.txt` |
| Outbox backlog (**0 unpublished** at the end) | After → "Outbox backlog (orders → order-placed)" | `orders_outbox_unpublished` / `orders_outbox_published_total` from orders `/actuator/prometheus`; also `GET /api/stats .outboxUnpublished` |
| Payments pod deletion (**05:33:11Z**, 0 restarts) and outcomes | After → "Payments pod restarts & outcomes" | `kube_pod_container_status_restarts_total{container="payments"}`, `kube_pod_status_phase`, `payments_outcomes_total`; `verify-2/payments-pods-before-delete.txt`, `consumer-group-at-delete.txt` |
| Scheduling health (pods not ready, nodes without pod IPs) | After → "Pods not ready & nodes without pod IPs" | `kube_pod_container_status_waiting_reason{reason="ContainerCreating"}`, `awscni_total_ip_addresses == 0` |
| Scale-to-zero (**79 s**; payments 25 s) | "Replicas per service" | `verify-2/timestamps.txt`, `replicas-timeline.csv` |
| Reconciliation (1649 × 4, 0 dup, 0 missing) | — | `verify-2/reconciliation.md` / `.json` (database counts per service + k6 summary), `GET /api/stats` on each host |
| Reset time (437 s / 460 s) | — | `reset.sh` prints "reset complete in Ns"; `verify-1/reset.log` |

Prometheus lives in namespace `monitoring` and scrapes every ServiceMonitor/PodMonitor in the cluster; the
dashboard is a ConfigMap in `tkt01-after` labelled `grafana_dashboard: "1"`, so it is rebuilt by the reset and
removed by the teardown.

---

## 6. Fallback if the live run misbehaves

Do not debug on stage. Switch to the captures of the verified run — they are the same panels with the same numbers
the talk quotes:

| situation | do this |
|---|---|
| Grafana blank / slow | open `ticketing/evidence/tkt01/verify-2/dashboard-full.png` (both rows, 05:20–05:40Z) and the per-panel PNGs `panel-02-…` to `panel-15-…` in the same directory |
| k6 Job never starts (`k6 pod … never started`) | usually AWS credentials missing in the shell (`aws sts get-caller-identity`); the first launch of verify-2 failed exactly this way and fired nothing. Re-export the AWS pair and re-run. If there is no time, narrate from `verify-2/k6-summary.json` |
| payments does not reach 6/6 before you want to delete a pod | delete one anyway once ≥ 2 are Running; the argument is offset-after-commit, not the count |
| pods stuck `ContainerCreating` | the "Pods not ready & nodes without pod IPs" panel shows it; this is the verify-1 failure (`verify-1/stuck-pods-on-bad-node.txt`). Narrate the fix from verify-1 → verify-2 and use the verify-2 captures |
| reset fails on the certificate wait | §2: run `ticketing/load/seed.sh tkt01` by hand; TLS is fine via the wildcard |
| the numbers on stage differ from the ones above | expected within a few percent; the exact reconciled run is `20260929t053124`, report `verify-2/reconciliation.md`, and verify attempt 1 (`verify-1/reconciliation.md`) shows what a failing run looked like and why |

Both reconciliation reports and every capture are committed on the PR branch, so the PR alone is enough to give
the talk without a cluster.

---

## 7. Sessions (every stage of run `tkt01`)

| stage | session |
|---|---|
| orchestrator (workflow run view) | <https://partner-workshops.devinenterprise.com/sessions/cc9e6c3bc8ae4ced9ed05049c8ab0097> |
| assess (decomposition note) | <https://partner-workshops.devinenterprise.com/sessions/540e1ed6a2f64332aeea95e7c4276a2c> |
| build — orders | <https://partner-workshops.devinenterprise.com/sessions/5208166a36db4861ad40f075dbf747b2> |
| build — seats | <https://partner-workshops.devinenterprise.com/sessions/7d963d5164304e60bb64815116c9cd99> |
| build — payments | <https://partner-workshops.devinenterprise.com/sessions/930473be4b294ff7afcb457ea6da1fcb> |
| build — confirmations | <https://partner-workshops.devinenterprise.com/sessions/702d03bce06442ebbee754dd54b6a524> |
| integrate | <https://partner-workshops.devinenterprise.com/sessions/f1e74a0cc6fe44cdb9aab5656fcc5055> |
| verify — attempt 1 (FAIL: 2 of 4 shape checks) | <https://partner-workshops.devinenterprise.com/sessions/fbd698d78f384dc29d9cb6e284aeb9da> |
| fix — payments (outbox relay for the inbox fan-out) | <https://partner-workshops.devinenterprise.com/sessions/887cce0cc68e46e3aa65b0edd0981b37> |
| fix — confirmations (consume payment-captured from Kafka) | <https://partner-workshops.devinenterprise.com/sessions/c4b45980d084473cb52760ef8a7990cf> |
| fix — integration (pod-IP capacity preflight, rebase/retag) | <https://partner-workshops.devinenterprise.com/sessions/4a42222bc9314d43a205a80e7e7041e5> |
| verify — attempt 2 (PASS: 4 of 4) | <https://partner-workshops.devinenterprise.com/sessions/7be0eecd860c410c9bbe5727c357796e> |
| ship (this runbook, the PR, Devin Review) | <https://partner-workshops.devinenterprise.com/sessions/80c6b5e22ed4451191c7ab350007ce0d> |

---

## 8. Teardown

```bash
make demo-destroy NS=tkt01            # → ticketing/scripts/destroy.sh tkt01
```

Deletes both namespaces and everything else labelled `demo.otterworks.app/run-token=tkt01` (cluster-scoped objects,
ECR image tags prefixed `tkt01-`, the Route53 records external-dns created for the two hosts), then lists what is
left and **exits non-zero if anything survives** — treat a non-zero exit as a bug to report, not something to clean
by hand. `make demo-destroy NS=tkt01 DRY_RUN=1` prints the plan first.

Measured on throwaway tokens so `tkt01` stays up for the demo (transcripts in `ticketing/evidence/tkt01/lifecycle/`):

| run | command | result |
|---|---|---|
| `tkt02` | `make ticketing-reset NS=tkt02` | both namespaces built and seeded in 440 s, certificate issued normally |
| `tkt02` | `make demo-destroy NS=tkt02` | `PASS: nothing carrying tkt02 remains (263s)` |
| `tkt03` | `make ticketing-reset NS=tkt03`, `smoke.sh tkt03` | 444 s; purchase CONFIRMED on both sides with the non-root security contexts |
| `tkt03` | `make demo-destroy NS=tkt03` | `PASS: nothing carrying tkt03 remains (265s)` |
| `tkt01` | `make demo-destroy NS=tkt01 DRY_RUN=1` | plan only; lists both namespaces and the `tkt01-*` image tags |

Destroying `tkt01` also deletes the `tkt01-*` service image tags that `deploy/after/images.sh` pins, so a later
`make ticketing-reset NS=tkt01` needs those images rebuilt first. To rehearse the teardown before an event, reset
and destroy a scratch token (as above) instead of the demo token.

Do not run it while the namespaces are still needed for a review; both were deliberately left running at the
at-rest shape in §3 after verify attempt 2.
