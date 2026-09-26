# 07_dependency_register

States: FOUND, DECIDED (owner and plan named), DONE. Filled by playbook 2 from the DDL census and app-code inspection.

| ID | Class | Object | What it does | State | Owner / plan |
|---|---|---|---|---|---|
| D4-1 | D4 Access | source connectivity | none by policy (`offline`); no read-only Oracle principal exists or is requested | DECIDED | customer DBA (not present) must run live/snapshot recon in-network before STOP C |
| D4-2 | D4 Access | migration cluster | none by policy (`offline`); target is local `mongo:7` only | DECIDED | customer must provide a migration cluster for merge-grade recon before STOP C |
