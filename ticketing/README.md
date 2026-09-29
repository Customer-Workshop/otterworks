# Ticketing modernization demo

A synthetic ticketing monolith (`monolith/`, Jakarta EE 10 on WildFly) modernized by Devin into
event-driven services on the shared `otterworks-dev` cluster — as one dynamic workflow of child sessions.

| Path | What |
|---|---|
| `monolith/` | Before state: 13 session beans, 20 JSPs, 30 tables, nightly settlement, deterministic synthetic seed |
| `CONVENTIONS.md` | Names, token, labels, runtimes, routing and metrics every stage follows |
| `workflow/modernize.py` | The `run_workflow` script: assess → build ×4 → integrate → verify ⇄ fix (≤2) → ship |
| `workflow/run-config.json` | Run token, base branch, fix-round budget, the verification shape |
| `workflow/PLAYBOOK.md` | The orchestrator playbook (registered in the Demo org as `!ticketing_modernize`) |
| `platform/install.sh` | One-time cluster platform: Knative Serving + Kourier (ClusterIP), KEDA, Strimzi |
| `scripts/` | `deploy-before.sh`, `reset.sh`, `status.sh`, `destroy.sh` (all take the run token) |

```bash
make ticketing-before NS=tkt01     # monolith at 1 replica, CPU-limited, seeded
make ticketing-status NS=tkt01     # replica counts at rest
make ticketing-reset  NS=tkt01     # rebuild both namespaces + re-seed, one command
make demo-destroy     NS=tkt01     # delete everything carrying the token; fails if anything remains
```

Everything here is invented; no real company, person, venue or customer is named.
