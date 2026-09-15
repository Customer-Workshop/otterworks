#!/usr/bin/env python3
"""Turn a wave manifest's batch briefs into child-session prompts.

The fan-out workflow normally hands each batch brief to a child it launches itself. It
cannot run here (its pre-flight doctor starts in a process with no credentials), so the
orchestrator launches the same briefs as child Devin sessions. This script is the only
transformation applied: the brief is used verbatim, with a header that carries the two
things a session needs and a workflow-launched child would have been given by the runner -
which branch to start from, and the reporting shape the orchestrator collects.

Prompts are written to prompts/<wave>-<batch>.txt outside the repo working tree.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HEADER = """You are batch `{batch}` of wave {wave} in the OtterWorks pipeline-1 migration
factory, launched as a child session (the fan-out workflow runner has no credentials in its
process, so the orchestrator launches the same contract this way). Everything below the
line is your batch brief, unchanged.

Two things the brief cannot know:

1. START FROM `{work_branch}`, NOT the base branch. The plan, the wave-0 scaffolding, the
   Oracle JDBC recon driver and the mapping specs your brief tells you to read are on that
   branch; PR #1566 carries it into `{base_branch}` and has not merged yet. So:
   `git clone` the repo, `git checkout {work_branch}`, cut your unit branch from there, and
   open your PR with **base `{work_branch}`**. Do not target `{base_branch}`, `main` or
   `tech-partnerships`, and do not merge your own PR.
2. REPORT BACK IN THE SESSION. You cannot write to the orchestrator's session and you must
   not edit `.migration/` outside `.migration/recon/<your unit>/`. Finish with a
   message_user that states, per unit: status (PASS / FAIL / BLOCKED), the recon verdict and
   its grade, the PR link, the evidence path, and any dialect rule you had to derive
   (skill_feedback). If you halt, say which control halted you.

Recon on this run is DEGRADED by the owner's decision (D10-01 denied, no Lakehouse
Federation): use `databricks/migration/recon/run_degraded_recon.py`, which drives the real
harness with a repo-local Oracle JDBC adapter. Never call a degraded result an official
harness verdict, anywhere.

----------------------------------------------------------------------------------------
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--work-branch", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text())
    args.out.mkdir(parents=True, exist_ok=True)
    for batch in manifest["batches"]:
        header = HEADER.format(batch=batch["id"], wave=manifest["wave"],
                               work_branch=args.work_branch,
                               base_branch=manifest["base_branch"])
        path = args.out / f"wave-{manifest['wave']}-{batch['id']}.txt"
        path.write_text(header + batch["brief"])
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
