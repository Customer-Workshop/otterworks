"""INIT: apply target.ddl_dir (idempotent, tracked in mig.schema_version), the archive store's ddl_dir for a
split target, reader user, --apply-sql / --apply-archive-sql files."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from ..context import RunContext
from ..drivers.base import ArchiveStoreTarget
from ..errors import ConfigError

READER_USER_ENV = "AZSQL_READER_USER"
READER_PASSWORD_ENV = "AZSQL_READER_PASSWORD"  # noqa: S105 - env var name, not a secret


def ddl_files(ddl_dir: Path) -> list[Path]:
    if not ddl_dir.is_dir():
        raise ConfigError(f"target.ddl_dir {ddl_dir} is not a directory")
    return sorted(p for p in ddl_dir.iterdir() if p.suffix.lower() == ".sql")


def archive_store(ctx: RunContext) -> ArchiveStoreTarget | None:
    """The split target's archive half, when the manifest configures one."""
    if ctx.manifest.target.archive is None:
        return None
    if not isinstance(ctx.target, ArchiveStoreTarget):
        raise ConfigError(f"target.archive is set but the {ctx.manifest.target.provider} driver has no archive store")
    return ctx.target


def apply_ddl(ctx: RunContext) -> list[str]:
    """Apply every DDL file whose content changed since it was last recorded. Returns the applied names."""
    ddl_dir = ctx.loaded.resolve(ctx.manifest.target.ddl_dir)
    applied = ctx.target.applied_ddl()
    done: list[str] = []
    for path in ddl_files(ddl_dir):
        text = path.read_text(encoding="utf-8")
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if applied.get(path.name) == sha:
            continue
        ctx.target.apply_ddl(text, path.name, sha)
        ctx.log.info(f"applied {path.name} sha256={sha[:12]}")
        done.append(path.name)
    return done


def apply_archive_ddl(ctx: RunContext) -> list[str]:
    """Same as apply_ddl for target.archive.ddl_dir, tracked in the archive store's own MIG.SCHEMA_VERSION."""
    store = archive_store(ctx)
    if store is None:
        return []
    assert ctx.manifest.target.archive is not None
    ddl_dir = ctx.loaded.resolve(ctx.manifest.target.archive.ddl_dir)
    applied = store.applied_archive_ddl()
    done: list[str] = []
    for path in ddl_files(ddl_dir):
        text = path.read_text(encoding="utf-8")
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if applied.get(path.name) == sha:
            continue
        store.apply_archive_ddl(text, path.name, sha)
        ctx.log.info(f"applied archive {path.name} sha256={sha[:12]}")
        done.append(path.name)
    return done


def _read_script(ctx: RunContext, path: Path, flag: str) -> tuple[str, str, str]:
    repo_root = ctx.loaded.repo_root.resolve()
    resolved = path.resolve()
    if not resolved.is_file() or resolved.suffix.lower() != ".sql":
        raise ConfigError(f"{flag} {path}: not a .sql file")
    if not resolved.is_relative_to(repo_root):
        raise ConfigError(f"{flag} {path}: must live under the migration tree {repo_root}")
    text = resolved.read_text(encoding="utf-8")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return text, sha, str(resolved.relative_to(repo_root))


def run(
    ctx: RunContext, apply_sql: list[Path] | None = None, apply_archive_sql: list[Path] | None = None
) -> dict[str, dict[str, int]]:
    applied = apply_ddl(ctx)
    applied_archive = apply_archive_ddl(ctx)
    env = {**os.environ, **ctx.env}
    user, password = env.get(READER_USER_ENV), env.get(READER_PASSWORD_ENV)
    if user and password:
        ctx.target.ensure_reader(user, password)
        ctx.log.info(f"reader user {user} in role ldm_report_reader")
    elif user or password:
        raise ConfigError(f"{READER_USER_ENV} and {READER_PASSWORD_ENV} must be set together")
    for path in apply_sql or []:
        text, sha, rel = _read_script(ctx, path, "--apply-sql")
        ctx.target.apply_sql_in_namespace(text, ctx.namespace)
        ctx.log.info(f"applied {rel} sha256={sha[:12]} ldm.namespace={ctx.namespace}")
    if apply_archive_sql:
        store = archive_store(ctx)
        if store is None:
            raise ConfigError("--apply-archive-sql requires a manifest with target.archive")
        for path in apply_archive_sql:
            text, sha, rel = _read_script(ctx, path, "--apply-archive-sql")
            store.apply_archive_sql_in_namespace(text, ctx.namespace)
            ctx.log.info(f"applied archive {rel} sha256={sha[:12]} LDM_NAMESPACE={ctx.namespace}")
    counts = {"applied": len(applied), "scripts": len(apply_sql or [])}
    if ctx.manifest.target.archive is not None:
        counts.update(archive_applied=len(applied_archive), archive_scripts=len(apply_archive_sql or []))
    return {"_ddl": counts}
