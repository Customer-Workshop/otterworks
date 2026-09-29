# Talk track: ticketing monolith to event-driven services (run `tkt01`)

Written to be said aloud. About eight minutes. Every number is from run `tkt01` on the shared cluster; the
sources are in `ticketing/evidence/tkt01/verify-2/reconciliation.md` and the session list in the runbook.

## Opening (first minute)

A ticketing company sizes its whole estate for the biggest on-sale of the year. For the other fifty-one weeks the
application servers sit idle, and on the day itself the traffic arrives at fifty times the normal rate inside a few
minutes. The application is a Jakarta EE monolith on an application server, and nobody has had the quarter it
would take to pull it apart.

We gave that program to Devin as one assignment. Devin read the monolith, wrote the decomposition, built four
services at the same time in four separate sessions, deployed them next to the original, ran the on-sale against
both, killed the payment consumer in the middle of the spike, found what broke, fixed it, ran it again, and opened a
pull request for review. Nobody provisioned a machine for any of that work. Each stage
started on its own cloud workstation the moment the stage before it handed over a branch.

## The run view (tab 1)

This is the orchestrator session. It ran one workflow script, and every stage you see is a separate Devin session
with its own machine and its own record: one assessment, four builds, one integration, two verification attempts
with a fix round between them, and one shipping session. Thirteen sessions in all.

Look at the four build sessions. They started within three seconds of each other and worked in parallel for about
an hour, each on its own service, each pushing its own branch. The number of Devins working at once is a budget
line, not a hiring plan. The ACUs are listed per stage here, so the cost of every step is visible next to the work
it bought.

## The assessment (tab 2)

Devin's first deliverable was understanding. This is the decomposition note, and every claim in it links to the
line of source it came from. Here is the session bean it is describing: `PurchaseFacadeBean.completeHold`, which
runs customers, holds, pricing, orders, payments and confirmations inside one transaction. The note gives each of
the thirty tables one owner, names the events between the contexts, and picks the first slice to extract: order
placement, seat allocation, payment and confirmation. The four build sessions coded against this note as their
contract.

## The on-sale (tab 3, Grafana)

The top row is the monolith: one replica with a fixed limit of half a CPU. The bottom row is the four services.
One load generator in the cluster fires the same on-sale at both, six hundred orders a minute each, through the
same ingress.

The monolith pins its CPU at the limit and tops out at about two hundred and sixty orders a minute. Its 95th
percentile latency goes past thirty seconds, and more than a third of the requests are turned away.

Underneath, the services take all six hundred orders a minute with a 95th percentile of about a quarter of a
second. Watch the replica panel: every service starts at zero, steps up to at most six, and stops there because six
is the cap we set.

The run is sized to show the shape, not the customer's volume. The same caps are variables, and the fifty-times
spike is a matter of raising them.

## The failure (still tab 3)

In the middle of the spike we deleted one of the payment consumer pods. The partition it was reading replays to
the surviving consumers from the last committed offset, the lag climbs and then drains, and the payment service
records each order once because the order reference is the idempotency key.

## The reconciliation (tab 4)

Here is the report. On the services side, 1,649 orders fired, 1,649 placed, 1,649 paid, 1,649 confirmed, zero
duplicates, zero missing. Every service except seats, which a per-minute sweep keeps warm, was back at zero
replicas seventy-nine seconds after the spike ended.

That clean result took two attempts. On the first attempt the same pod kill left six of 1,649 orders paid. Devin's
verification session wrote down why: the payment consumer waited forever on a synchronous call to confirmations,
and new cluster nodes could not hand out pod addresses. The workflow sent each finding to the session that owned
that part of the system. Payments moved the call behind an outbox, confirmations started reading its events from
Kafka, and the integration session added a capacity check to the deploy. The second verification passed all four
checks. The failure, the diagnosis and the fix are all in the trail, and that is the part a reviewer should read.

## The pull request (tab 5)

The shipping session opened this pull request with the decomposition note, the reports, the runbook and a link to
every session in the run. The repository's security scan ran on it, and it goes to Devin Review and then to the
team's own reviewers. Nothing is merged; the team's own review and pipeline decide that.

## In the customer's cloud

On a cloud provider the same design maps to managed Kubernetes for the cluster, a serverless container runtime for
the request-driven services, a managed streaming service in place of the Kafka cluster, and a managed relational
database for each service's PostgreSQL.

## Close

Everything you just watched ran without a presenter in the loop. Devin took one assignment, split it, ran the parts
at once, tested its own work under failure, fixed what it found, and handed back a pull request with the
evidence attached. Your team keeps its editor, its review and its pipeline. Devin takes the program that never
gets scheduled.
