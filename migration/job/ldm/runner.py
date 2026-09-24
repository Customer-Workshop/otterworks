"""Wires manifest + drivers + staging into a RunContext and runs stage verbs with contract exit codes."""

from __future__ import annotations

import json
import os
import sys
import traceback
from collections.abc import Callable, Mapping
from pathlib import Path

from .config import RUN_ID_RE, LoadedManifest, load_manifest
from .context import Log, RunContext, build_table_specs, local_staging_dir, require_env
from .drivers.base import SourceDriver, TargetDriver
from .errors import EXIT_OK, EXIT_UNEXPECTED, ConfigError, LdmError
from .stages import extract, init, load, purge, reconcile, validate
from .staging import AzureBlobStore, BlobStore, NoBlobStore

STAGES: dict[str, Callable[[RunContext], dict[str, dict[str, int]]]] = {
    "extract": extract.run,
    "load": load.run,
    "validate": validate.run,
    "purge": purge.run,
    "reconcile": reconcile.run,
}
ALL_ORDER = ("extract", "load", "validate", "purge", "reconcile")
HOSTS = ("eks", "aca", "local")


def validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.match(run_id):
        raise ConfigError(f"--run-id {run_id!r} must match {RUN_ID_RE.pattern}")
    return run_id


def make_source(loaded: LoadedManifest, env: Mapping[str, str]) -> SourceDriver:
    src = loaded.manifest.source
    if src.driver == "db2":
        from .drivers.db2 import Db2Source

        ce = src.connection_env
        require_env(dict(env), [ce.host, ce.port, ce.database, ce.user, ce.password], "source db2")
        return Db2Source(
            host=env[ce.host],
            port=int(env[ce.port]),
            database=env[ce.database],
            user=env[ce.user],
            password=env[ce.password],
        )
    raise ConfigError(f"source.driver {src.driver!r} has no driver in this build (known: db2)")


def make_target(loaded: LoadedManifest, env: Mapping[str, str]) -> TargetDriver:
    tgt = loaded.manifest.target
    if tgt.provider == "azuresql":
        from .drivers.azuresql import AzureSqlTarget

        ce = tgt.connection_env
        auth = env.get(ce.auth_mode) or "sql"
        require_env(dict(env), [ce.server, ce.database], "target azuresql")
        if auth == "sql":
            require_env(dict(env), [ce.user, ce.password], "target azuresql (AZSQL_AUTH=sql)")
        elif auth == "managed-identity":
            require_env(dict(env), [ce.managed_identity_client_id], "target azuresql (AZSQL_AUTH=managed-identity)")
        else:
            raise ConfigError(f"{ce.auth_mode}={auth!r}: expected 'sql' or 'managed-identity'")
        return AzureSqlTarget(
            server=env[ce.server],
            database=env[ce.database],
            auth=auth,
            user=env.get(ce.user),
            password=env.get(ce.password),
            client_id=env.get(ce.managed_identity_client_id),
        )
    raise ConfigError(f"target.provider {tgt.provider!r} has no driver in this build (known: azuresql)")


def make_blobs(loaded: LoadedManifest, env: Mapping[str, str]) -> BlobStore:
    ce = loaded.manifest.staging.connection_env
    account = env.get(ce.storage_account)
    if not account:
        return NoBlobStore()
    container = env.get(ce.container)
    if not container:
        raise ConfigError(f"{ce.storage_account} is set but {ce.container} is not")
    return AzureBlobStore(account, container, env.get("AZ_STORAGE_KEY"), env.get("AZURE_CLIENT_ID"))


def build_context(
    manifest_path: Path,
    namespace: str,
    run_id: str,
    env: Mapping[str, str] | None = None,
    source: SourceDriver | None = None,
    target: TargetDriver | None = None,
    blobs: BlobStore | None = None,
    log: Log | None = None,
) -> RunContext:
    env = dict(os.environ if env is None else env)
    loaded = load_manifest(manifest_path, namespace)
    host = env.get("LDM_HOST") or "local"
    if host not in HOSTS:
        raise ConfigError(f"LDM_HOST={host!r}: expected one of {HOSTS}")
    tables = build_table_specs(loaded)
    ctx = RunContext(
        loaded=loaded,
        run_id=run_id,
        source=source if source is not None else make_source(loaded, env),
        target=target if target is not None else make_target(loaded, env),
        blobs=blobs if blobs is not None else make_blobs(loaded, env),
        local_dir=local_staging_dir(loaded.manifest, env),
        log=log or Log(),
        env=env,
        tables=tables,
    )
    for ts in ctx.tables_in_order():
        ctx.target.register_table(ts.name, ts.config.key_columns, ts.config.hash_columns, ts.columns)
    return ctx


def prepare_run(ctx: RunContext) -> None:
    """DDL part of init, then mig.runs / mig.run_ledger rows for this run (every stage verb)."""
    ctx.log.stage = "INIT"
    init.apply_ddl(ctx)
    m = ctx.manifest
    ctx.target.ensure_run(ctx.run_id, ctx.namespace, m.purge, ctx.env.get("LDM_JOB_IMAGE"), ctx.loaded.sha256)
    ctx.target.ensure_ledger(ctx.run_id, ctx.namespace, [(t.name, t.order, t.role) for t in m.tables_in_order()])
    status = ctx.target.get_run_status(ctx.run_id, ctx.namespace)
    if status in ("CLOSED",):
        raise ConfigError(f"run {ctx.run_id} in {ctx.namespace} is already CLOSED; use a new --run-id")
    if status == "FAILED":
        ctx.log.warn(f"run {ctx.run_id} previously FAILED; resuming")
        ctx.target.set_run_status(ctx.run_id, ctx.namespace, "RUNNING", None)


def run_stage(ctx: RunContext, stage: str) -> dict[str, dict[str, int]]:
    ctx.log.stage = stage.upper()
    ctx.log.info(f"start run_id={ctx.run_id} namespace={ctx.namespace} host={ctx.env.get('LDM_HOST') or 'local'}")
    result = STAGES[stage](ctx)
    ctx.log.info("done")
    return result


def execute(ctx: RunContext, verb: str, apply_sql: list[Path] | None = None) -> tuple[int, dict[str, dict[str, int]]]:
    """Run a verb; returns (exit_code, tables). Never raises for LdmError - the code carries it."""
    tables: dict[str, dict[str, int]] = {}
    try:
        ctx.source.connect() if verb in ("extract", "purge", "all") else None
        ctx.target.connect()
        if verb == "init":
            ctx.log.stage = "INIT"
            tables = init.run(ctx, apply_sql)
            return EXIT_OK, tables
        prepare_run(ctx)
        stages = ALL_ORDER if verb == "all" else (verb,)
        for stage in stages:
            for name, counts in run_stage(ctx, stage).items():
                tables.setdefault(name, {}).update(counts)
        return EXIT_OK, tables
    except LdmError as e:
        ctx.log.error(f"{type(e).__name__}: {e}")
        for name, counts in e.tables.items():
            tables.setdefault(name, {}).update(counts)
        if e.exit_code != EXIT_OK and verb != "init":
            _mark_failed(ctx, e.exit_code)
        return e.exit_code, tables
    except Exception as e:  # noqa: BLE001 - contract: any other error is exit 1 with the traceback on stderr
        ctx.log.error(f"unexpected {type(e).__name__}: {e}")
        traceback.print_exc(file=sys.stderr)
        if verb != "init":
            _mark_failed(ctx, EXIT_UNEXPECTED)
        return EXIT_UNEXPECTED, tables
    finally:
        for drv in (ctx.source, ctx.target):
            try:
                drv.close()
            except Exception:  # noqa: BLE001, S110 - best effort on shutdown
                pass


def _mark_failed(ctx: RunContext, exit_code: int) -> None:
    try:
        if ctx.target.get_run_status(ctx.run_id, ctx.namespace) == "RUNNING":
            ctx.target.set_run_status(ctx.run_id, ctx.namespace, "FAILED", exit_code)
    except Exception as e:  # noqa: BLE001 - the original failure is what the caller must see
        ctx.log.error(f"could not mark run FAILED: {e}")


def emit_result(run_id: str, namespace: str, stage: str, exit_code: int, tables: dict[str, dict[str, int]]) -> None:
    print(
        json.dumps(
            {
                "run_id": run_id,
                "namespace": namespace,
                "stage": stage,
                "exit_code": exit_code,
                "tables": tables,
            }
        )
    )
