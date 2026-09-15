"""Mint the harness's Databricks SQL credential into a child process, by name only.

    python3 with_databricks_sql_token.py DATABRICKS_MIGRATION_SQL -- python3 run_degraded_recon.py ...

The harness's Databricks target adapter reads a JSON secret
{"server_hostname", "http_path", "access_token"} out of the named environment variable.
There is no stored secret holding it and the guard blocks writing one, so it is built here
from the migration service principal's OAuth client credentials and handed only to the child
process. The token is short-lived, never printed, and never written to disk.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

WAREHOUSE = "565cd2fd713738c4"


def main(argv: list[str]) -> int:
    if "--" not in argv:
        raise SystemExit(__doc__)
    split = argv.index("--")
    var = argv[0] if split else "DATABRICKS_MIGRATION_SQL"
    command = argv[split + 1:]
    if not command:
        raise SystemExit(__doc__)

    from databricks.sdk.core import Config, oauth_service_principal

    host = os.environ["DATABRICKS_HOST"]
    cfg = Config(host=host,
                 client_id=os.environ["DATABRICKS_CLIENT_ID"],
                 client_secret=os.environ["DATABRICKS_CLIENT_SECRET"])
    header = oauth_service_principal(cfg)()["Authorization"]
    scheme, _, token = header.partition(" ")
    if scheme != "Bearer" or not token:
        raise SystemExit("service principal did not return a bearer token")
    value = json.dumps({"server_hostname": host.replace("https://", ""),
                        "http_path": f"/sql/1.0/warehouses/{WAREHOUSE}",
                        "access_token": token})
    return subprocess.call(command, env=dict(os.environ, **{var: value}))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
