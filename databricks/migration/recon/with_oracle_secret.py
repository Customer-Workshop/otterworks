"""Fetch the read-only Oracle secret into a child process's environment, by name only.

    python3 with_oracle_secret.py OW_TP_ORACLE_RO -- python3 run_degraded_recon.py ...

The value is never printed, written to disk, or added to this process's own environment
beyond the child it launches.
"""

from __future__ import annotations

import os
import subprocess
import sys

DEFAULT_SECRET = "ow-tp/oracle/ow_billing_ro"
REGION = "us-east-1"


def main(argv: list[str]) -> int:
    if "--" not in argv:
        raise SystemExit(__doc__)
    split = argv.index("--")
    var = argv[0] if split else "OW_TP_ORACLE_RO"
    secret_id = argv[1] if split > 1 else DEFAULT_SECRET
    command = argv[split + 1:]
    if not command:
        raise SystemExit(__doc__)

    import boto3

    value = boto3.client("secretsmanager", region_name=REGION).get_secret_value(
        SecretId=secret_id)["SecretString"]
    env = dict(os.environ, **{var: value})
    return subprocess.call(command, env=env)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
