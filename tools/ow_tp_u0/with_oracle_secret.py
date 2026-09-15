from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping


SECRET_ID = "ow-tp/oracle/ow_billing_ro"
SECRET_ENV = "ORACLE_OW_BILLING_RO_DSN"


def _secret_payload() -> Mapping[str, object]:
    completed = subprocess.run(
        [
            "aws",
            "secretsmanager",
            "get-secret-value",
            "--secret-id",
            SECRET_ID,
            "--region",
            "us-east-1",
            "--query",
            "SecretString",
            "--output",
            "json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    secret_string = json.loads(completed.stdout)
    payload = json.loads(secret_string)
    if not isinstance(payload, Mapping):
        raise RuntimeError("Oracle secret payload is not a JSON object")
    return payload


def _dsn(payload: Mapping[str, object]) -> str:
    value = payload.get("dsn")
    if not value:
        user = payload.get("user", payload.get("username"))
        password = payload.get("password")
        host = payload.get("host")
        port = payload.get("port")
        service = payload.get("service", payload.get("service_name"))
        if not all((user, password, host, port, service)):
            raise RuntimeError("Oracle secret has neither dsn nor complete connection fields")
        value = f"{user}/{password}@{host}:{port}/{service}"
    if not isinstance(value, str) or not value:
        raise RuntimeError("Oracle secret dsn is not a non-empty string")
    return value


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("usage: with_oracle_secret.py COMMAND [ARGS ...]")
    dsn = _dsn(_secret_payload())
    print(
        "oracle_secret_dsn_shape "
        f"len={len(dsn)} has_at={'@' in dsn} has_slash={'/' in dsn}",
        file=sys.stderr,
    )
    env = os.environ.copy()
    env[SECRET_ENV] = dsn
    os.execvpe(sys.argv[1], sys.argv[1:], env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
