"""Launcher for the migration-fanout Cloud backend (workflow.py, unmodified).

run_workflow does not pass environment variables to the script and starts it in $HOME, while
workflow.py reads WAVE_MANIFEST / WAVE_RUN_ID / WAVE_RESUME from the environment relative to
the repo root. This wrapper sets them from the file below and from the shim's run id, then
executes workflow.py in this interpreter with the shim's runtime globals. Nothing in
workflow.py (its guards, breaker, verifier, result/brief writers) is changed. Decision D-008.

.migration/waves/fanout.env: one KEY=VALUE per line (WAVE_MANIFEST relative to repo root,
optional WAVE_RESUME=1 / WAVE_RERUN=1).
"""
import glob
import os
import runpy

REPO_ROOT = "/home/ubuntu/repos/otterworks"
WORKFLOW = sorted(glob.glob(
    "/opt/.devin/plugins/cache/*mongo-migration-plugin*/*/skills/migration-fanout/workflow.py"))[-1]

os.chdir(REPO_ROOT)
with open(".migration/waves/fanout.env") as fh:
    for line in fh:
        line = line.strip()
        if line and not line.startswith("#"):
            k, _, v = line.partition("=")
            os.environ[k] = v
os.environ["WAVE_RUN_ID"] = _DEVIN_WORKFLOW_RUN_ID  # noqa: F821 (shim global)
log(f"fanout launcher: {WORKFLOW} manifest={os.environ['WAVE_MANIFEST']} run_id={os.environ['WAVE_RUN_ID']}")  # noqa: F821
runpy.run_path(WORKFLOW, init_globals=dict(globals()), run_name="__main__")
