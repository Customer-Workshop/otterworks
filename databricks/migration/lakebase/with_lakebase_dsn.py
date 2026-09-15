"""Mint a short-lived Lakebase DSN into a child process's environment, by name only.

    python3 with_lakebase_dsn.py OW_TP_LAKEBASE_DSN mig-p1-w1 -- python3 apply_sql.py x.sql

The OAuth credential is minted by `databricks postgres generate-database-credential` for the
migration principal, lives about an hour, and is only ever placed in the child's environment:
never printed, never written to disk, never added to this process's own environment.

The branch is an argument rather than a constant because each wave runs on its own branch.
It is checked against `.migration/allowed_targets.json` before a credential is requested, so
a typo cannot mint a token for `production` or for another project's branch.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# The DSN goes into a variable of this shape and no other, so a mistyped first argument
# cannot land a credential in PATH or in a variable the child reads for something else.
VAR_NAME = re.compile(r"^OW_TP_[A-Z0-9_]+$")
PROJECT = "ow-tp-billing"
DATABASE = "ow_tp"
ALLOWED_TARGETS = Path(".migration/allowed_targets.json")


def _cli(*args: str) -> dict:
    out = subprocess.run(["databricks", *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"databricks {' '.join(args)} failed: {out.stderr.strip()}")
    return json.loads(out.stdout)


def dsn(branch: str) -> str:
    allowed = json.loads(ALLOWED_TARGETS.read_text())
    if PROJECT not in allowed.get("lakebase_projects", []):
        raise SystemExit(f"project {PROJECT!r} is not in {ALLOWED_TARGETS}")
    if branch not in allowed.get("lakebase_branches", []):
        raise SystemExit(f"branch {branch!r} is not in {ALLOWED_TARGETS}")

    endpoint = f"projects/{PROJECT}/branches/{branch}/endpoints/primary"
    (ep,) = _cli("postgres", "list-endpoints", f"projects/{PROJECT}/branches/{branch}")
    # The pooled host rejects the generated OAuth credential (SASL authentication failed);
    # migration sessions connect to the endpoint host directly.
    host = ep["status"]["hosts"]["host"]
    me = _cli("current-user", "me")
    token = _cli("postgres", "generate-database-credential", endpoint)["token"]
    return (f"host={host} port=5432 dbname={DATABASE} user={me['userName']} "
            f"password={token} sslmode=require")


def main(argv: list[str]) -> int:
    if "--" not in argv or argv.index("--") < 2:
        raise SystemExit(__doc__)
    split = argv.index("--")
    var, branch = argv[0], argv[1]
    if not VAR_NAME.match(var):
        raise SystemExit(f"refusing to set {var!r}: the DSN variable must match {VAR_NAME.pattern}")
    command = argv[split + 1:]
    if not command:
        raise SystemExit(__doc__)
    return subprocess.call(command, env=dict(os.environ, **{var: dsn(branch)}))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
