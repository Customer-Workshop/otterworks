# Portal CI/CD runbook

How a commit reaches production for the decomposed portal, what it replaces, and where the
rollback comes from in each path.

- Pipeline: [`.github/workflows/portal-cicd.yml`](../../.github/workflows/portal-cicd.yml)
- Charts: `infrastructure/helm/{announcements,user-preferences,feedback}-service`
- Databases and ECR repositories: `infrastructure/terraform/modules/portal`, `platform/terraform/main.tf`
- Routing model and rollback story: [`traffic-routing.md`](traffic-routing.md)
- Shutting the shell off: [`decommission.md`](decommission.md)

This pipeline **cannot go green today**. The reasons are pre-existing estate problems, they
are listed in [Before this pipeline can pass](#before-this-pipeline-can-pass), and the correct
response to each is to fix the estate, not the gate.

---

## Today: a commit to `services/legacy-portal`

What an operator does now, on the on-prem host that runs the portal
([`services/legacy-portal/README.md`](../../services/legacy-portal/README.md),
[`deploy/legacy-portal.service`](../../services/legacy-portal/deploy/legacy-portal.service)):

1. Merge the change. Nothing happens; no pipeline builds or deploys the portal.
2. SSH to the portal host.
3. `git pull` in the working copy on the host, then `./scripts/run-onprem.sh`, which runs
   `./mvnw -B -DskipTests package` — **on the production host, with tests skipped** — and
   produces `target/legacy-portal-*.jar`.
4. Copy the jar over the running one: `cp target/legacy-portal-*.jar /opt/legacy-portal/legacy-portal.jar`.
5. `sudo systemctl restart legacy-portal`. The service is down from the moment the old
   process stops until Spring finishes booting: a single process, no second instance, no
   draining. `Restart=on-failure` restarts a crash, it does not shorten the gap.
6. Check by hand: `curl http://localhost:8095/health`, and eyeball the logs.

Properties of this path worth naming, because the pipeline below is designed against them:

- **The artifact is whatever the host built.** It is not the artifact anything was tested
  against, and the same commit built on a different host may not be the same jar.
- **Nothing is a gate.** Tests, a vulnerability scan, and parity are things a person may or
  may not have run somewhere else.
- **Rollback is a jar you hope is still there.** The previous
  `/opt/legacy-portal/legacy-portal.jar` was overwritten in step 4. Recovery means finding
  the previous build (or rebuilding an older commit on the host, several minutes) and
  restarting again. If nobody kept a copy, the rollback is a build, not a restore.
- **"Healthy" is a person's judgement**, made once, at the moment they looked.

## Under this pipeline: a commit to the decomposed portal

Push to `demo/legacy-portal-migration` (or open a PR against it) touching the portal services,
the parity harness, the charts, the portal Terraform, or the workflow itself:

| # | Job | What it does | On failure |
|---|-----|--------------|------------|
| 1 | `build` | Compiles the three extracted services (Java 21 reactor), the legacy shell (Java 11), and the client app. | Stops. Nothing downstream runs. |
| 2 | `test` | `make portal-build` — each service's suite, including a Testcontainers PostgreSQL 16 that Flyway migrates from empty, so the schema is proven before a pod ever applies it. Plus the shell's suite and the client app's lint/tests. | Stops. |
| 3 | `parity` | Starts the **pinned pre-retirement monolith** on 8096 and the extracted services on 8101-8103, then replays all three contexts through the frozen harness (`tests/parity/portal/replay.py`), comparing status and full JSON body. | Stops. Also stops, by design, when the pinned reference is not published — see below. |
| 4a | `dependency behavior gate` | Calls [`deps-remediation.yml`](../../.github/workflows/deps-remediation.yml) unchanged as a required job: it proves the recorded before-state still reproduces. | Blocks the push job. Green today. |
| 4b | `dependency CVE gate` | Runs the same advisory harness and fails on its exit code: vulnerable (1) and no-verdict (2) both fail. | Blocks the push job. **Red today.** |
| 5 | `ECR repository cross-check` | Asserts every image the workflow pushes has a repository declared in `platform/terraform/main.tf`. | Stops before anything is built. |
| 6 | `image scan` | Builds each image locally (`load`, not `push`) and scans it with Trivy at CRITICAL/HIGH, same version and `.trivyignore` as `security-scan.yml`. | Stops. An unscanned image never reaches the registry. |
| 7 | `push` | Pushes each image to `otterworks/<image>:<commit sha>` in ECR. Repositories are IMMUTABLE, so a tag is one exact set of bytes, forever. | Stops. Not run at all for a pull request. |
| 8 | `deploy` | `helm upgrade --install --wait` for the three releases, pinned to this commit's tag. | Rollback (step 10). |
| 9 | `health gate` | From inside the cluster, `GET http://<release>:<port>/health` for each context and asserts the body identifies **that** service. | Rollback (step 10). |
| 10 | `rollback` | `helm rollback <release> 0` for each release: previous revision, previous image tag and previous config, together. | Reported; the run fails. |

Answering the same questions as the list above:

- **The artifact is the one that was tested.** One image per commit, built once, scanned, then
  pushed under an immutable tag and deployed by digest-stable tag. No host builds anything.
- **Every check is a gate**, in an order chosen so nothing unproven moves forward: tests before
  parity, parity before the scan, the scan before the registry, both dependency gates before the push,
  the push before the cluster.
- **Rollback is a stored revision, not a hoped-for file.** Helm keeps the previous release
  revision; the previous image still exists in ECR because tags there are immutable. The
  rollback runs automatically within the same job, seconds after the gate fails.
- **"Healthy" is asserted**, from inside the cluster, on the exact address callers use.

### Why the health gate is not just readiness

`helm --wait` already waits for the readiness probe, which covers "the process is up and its
database answers". The gate asks the question readiness cannot: *is the right service
answering on the name and port the routing values point at?* `/health` echoes
`spring.application.name`, so a release installed under the wrong name, or a chart pointed at
another context's image, is caught by the pipeline instead of by a user reading someone else's
announcements. That failure mode is specific to this migration: three services that look alike,
one routing value each ([`traffic-routing.md`](traffic-routing.md)).

### Why the parity job fails when the reference is missing

Parity is only meaningful against the last build of the monolith that still served the three
contexts: `otterworks/legacy-portal:pre-retirement-c07b93bc`, built from commit `c07b93bc`
([`decommission.md`](decommission.md)). That image exists only on the machine that built it
(`validation-report.md`, open item 1), so the job requires a `PORTAL_REFERENCE_IMAGE` and fails
with publishing instructions when it is absent.

It deliberately does **not** fall back to the shell on 8095. The shell answers 404 for every
extracted route, so a replay against it would compare 404 to 404 for all 168 cases and report
perfect parity while proving nothing.

### Why the advisory is gated twice

`deps-remediation.yml` is reused as-is, but note what it actually grades. Its contract is
*behavioral*: when the vulnerable version is still reachable it grades the recorded **baseline**
transcript and passes, having proved the documented before-state still reproduces. That is the
right contract for that workflow and nothing here changes it — but it means it reports success
over a vulnerable tree, which is not a merge gate for a pipeline that pushes images.

So the advisory itself is gated separately, on the harness's own exit code, where vulnerable (1)
and no-verdict (2) both fail. That job is red, for pre-existing reasons, none created by the
extraction:

| Module | Finding |
|---|---|
| `report-service` | Depends on `commons-text` 1.9 directly — CVE-2022-42889. |
| `services/legacy-portal` | Reaches the same vulnerable `commons-text` transitively through `commons-configuration2:2.8.0`. This is an image **this pipeline pushes**. |
| `notification-service` | Depends on `commons-text` 1.9 directly (`build.gradle.kts:51`). It is unmeasurable locally without Gradle, where the harness returns "no verdict" (exit 2) — also not a pass; in CI its tree resolves and the verdict is VULNERABLE. |

The extracted `services/portal` reactor is measured and clean. Neither gate has
`continue-on-error`, `|| true` or an allowlist, so while the advisory is unresolved this pipeline
builds, tests, replays and scans, and ships nothing. Making the pipeline green means fixing those
three modules — in their own change, with their own review.

---

## Rollback: which one, when

Three different things get called "rollback" in this migration. They are not interchangeable.

**1. Release rollback (automatic, this pipeline).** The health gate fails, `helm rollback` puts
the previous revision of each extracted service back. Routing values never change: each context
still points at its own service name and port, now serving the previous image. This is the
normal case and needs no human.

**2. Routing rollback to a previous build (manual, minutes).** A problem found after the gate
passed. Redeploy the affected release at the previous known-good tag:

```bash
helm rollback announcements-service 0 -n <namespace>            # previous revision, or
helm upgrade announcements-service infrastructure/helm/announcements-service \
  -n <namespace> --reuse-values --set image.tag=<previous sha>
```

One context at a time; the other two are untouched. That independence is the point of the
extraction.

**3. Break-glass rollback to the monolith (manual, deliberate).** Documented in
[`traffic-routing.md`](traffic-routing.md) and [`decommission.md`](decommission.md), and
intentionally **not** automated. It requires the pinned pre-retirement image deployed first —
the shell at 8095 serves none of these routes and is not a rollback target — and anything
written to an extracted service's database since the cutover is not in the monolith's database.
The pipeline will not take that decision unattended.

---

## Before this pipeline can pass

Everything here is a human action outside this change. None of it is worked around in the
workflow.

1. **Publish the pinned pre-retirement reference.** Build or restore
   `otterworks/legacy-portal:pre-retirement-c07b93bc` from commit `c07b93bc`, push it to the
   `otterworks/legacy-portal` ECR repository, and set `PORTAL_REFERENCE_IMAGE` (preferably by
   digest) as a repository variable. Until then the `parity` job fails, and so does everything
   after it. This is also decommission pre-condition 6.
2. **Fix `report-service`'s direct CVE-2022-42889** (`commons-text` 1.9).
3. **Fix `notification-service`'s direct `commons-text` 1.9** (`build.gradle.kts:51`). Locally,
   without Gradle, the harness reaches no verdict on it (exit 2), which the gate also fails.
4. **Resolve the legacy shell's transitive `commons-text`** through
   `commons-configuration2:2.8.0`, or complete decommission step 6 and delete the shell — which
   also removes its image from this pipeline.
5. **Apply the Terraform.** `platform/terraform` for the `legacy-portal` and three portal-service ECR repositories,
   `infrastructure/terraform` for the three databases (`portal_db_passwords` must be supplied).
   Neither was applied by this change; no AWS resource exists yet.
6. **Configure the repository inputs** below.
7. **Create the `portal-migration` environment** and, if the cluster should not be deployed to
   on every push, put a required reviewer on it. The deploy job is bound to that environment.

### Repository inputs

| Kind | Name | Meaning |
|---|---|---|
| Variable | `PORTAL_REFERENCE_IMAGE` | Full reference to the pinned pre-retirement monolith image, digest preferred. |
| Variable | `PORTAL_JDBC_URLS` | JSON object, context → JDBC URL. The `portal_jdbc_urls` Terraform output. |
| Variable | `PORTAL_NAMESPACE` | Namespace for the three releases. Defaults to `otterworks-portal`. |
| Variable | `PORTAL_EKS_CLUSTER` | Cluster name. Defaults to `otterworks-dev`. |
| Secret | `PORTAL_DB_PASSWORDS` | JSON object, context → database password. Same keys as `PORTAL_JDBC_URLS`. |
| Secret | `AWS_ROLE_ARN` | Existing OIDC deploy role; must be able to pull and push the repositories below and run `helm` against the cluster. |

### ECR repositories

Declared in [`platform/terraform/main.tf`](../../platform/terraform/main.tf), all `IMMUTABLE`
with scan-on-push, all prefixed `otterworks/`. ECR does not create a repository on push, so the
`ECR repository cross-check` job asserts this list against the workflow's build matrix on every
run:

| Repository | Pushed by |
|---|---|
| `otterworks/announcements-service` | `push` matrix |
| `otterworks/user-preferences-service` | `push` matrix |
| `otterworks/feedback-service` | `push` matrix |
| `otterworks/legacy-portal` | `push` matrix; also hosts the pinned `pre-retirement-c07b93bc` reference |
| `otterworks/web-app` | `push` matrix — `frontend/client-app` publishes under this name, as it does in the estate's other pipelines |

### What this pipeline does not do

- It does not create AWS resources. Databases, ECR repositories and IAM live in Terraform;
  nothing in the charts provisions cloud infrastructure, and no chart declares a
  `LoadBalancer` Service (`AGENTS.md`).
- It does not expose the extracted services outside the cluster. They are `ClusterIP`, carry no
  authentication of their own, and are reached only through the client app's proxy prefixes.
- It does not deploy the legacy shell or the client app. Both images are built, scanned and
  pushed so the set is complete and rollback-able; their releases are owned by the existing
  deploy path until the shell is decommissioned.
