"""Point a child process at the LOCAL Oracle billing fixture, in the live secret's shape.

    python3 with_oracle_fixture.py OW_TP_ORACLE_FIXTURE -- python3 run_degraded_recon.py ...

Fixture-first development (01_conventions.md) needs a source that is not the real Oracle, so
this builds the same JSON the `ow-tp/oracle/ow_billing_ro` secret holds - `user`, `password`,
`host`, `port`, `service` - around the throwaway credentials of the container started by
`make oracle-billing-up` (see .agents/skills/oracle-billing-estate). They are the fixture's
published defaults and grant nothing outside a local container; no real secret is involved.

Everything downstream is unchanged, so a fixture run exercises the same adapter, mapping spec
and tolerances as the live run. A fixture verdict is never merge evidence.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

# The variable the fixture JSON is bound to is a secret-style name, never PATH, PYTHONPATH or
# anything else the child's runtime is resolved from.
SECRET_VAR = re.compile(r"^OW_TP_[A-Z0-9_]+$")

FIXTURE = {"user": "ow_billing", "password": "ow_billing", "host": "127.0.0.1",
           "port": os.environ.get("ORACLE_BILLING_DB_PORT", "52521"), "service": "FREEPDB1"}


def main(argv: list[str]) -> int:
    if "--" not in argv or argv.index("--") < 1:
        raise SystemExit(__doc__)
    split = argv.index("--")
    var = argv[0]
    if not SECRET_VAR.match(var):
        raise SystemExit(f"refusing to bind the fixture credentials to {var!r}: "
                         "the target variable must be named OW_TP_*")
    command = argv[split + 1:]
    if not command:
        raise SystemExit(__doc__)
    return subprocess.call(command, env=dict(os.environ, **{var: json.dumps(FIXTURE)}))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
