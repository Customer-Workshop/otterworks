"""Target driver construction from a picklable spec, so a Spark task can reopen the same target."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ..config import LoadedManifest
from ..context import require_env
from ..errors import ConfigError
from .base import TargetDriver


@dataclass(frozen=True)
class TargetSpec:
    """Provider name plus the keyword arguments of its driver constructor. Contains credentials: never log it."""

    provider: str
    kwargs: dict[str, object] = field(default_factory=dict)

    def open(self) -> TargetDriver:
        if self.provider == "postgresql":
            from .postgresql import PostgresTarget

            return PostgresTarget(**self.kwargs)  # type: ignore[arg-type]
        if self.provider == "azuresql":
            from .azuresql import AzureSqlTarget

            return AzureSqlTarget(**self.kwargs)  # type: ignore[arg-type]
        if self.provider == "snowflake":
            from .postgresql import PostgresTarget
            from .snowflake import SnowflakeArchive, SnowflakeTarget

            control = self.kwargs["control"]
            archive = self.kwargs["archive"]
            assert isinstance(control, dict) and isinstance(archive, dict)
            return SnowflakeTarget(PostgresTarget(**control), SnowflakeArchive(**archive))
        raise ConfigError(f"target.provider {self.provider!r} has no driver in this build")


def _postgres_kwargs(loaded: LoadedManifest, env: Mapping[str, str], host_kind: str) -> dict[str, object]:
    tgt = loaded.manifest.target
    ce = tgt.connection_env
    assert ce.host and ce.port
    require_env(dict(env), [ce.host, ce.port, ce.database, ce.user, ce.password], f"target {tgt.provider}")
    try:
        port = int(env[ce.port])
    except ValueError as e:
        raise ConfigError(f"{ce.port}={env[ce.port]!r} is not a port number") from e
    return {
        "host": env[ce.host],
        "port": port,
        "database": env[ce.database],
        "user": env[ce.user],
        "password": env[ce.password],
        "sslmode": (env.get(ce.sslmode) if ce.sslmode else None) or "prefer",
        "ldm_host": host_kind,
    }


def target_spec(loaded: LoadedManifest, env: Mapping[str, str]) -> TargetSpec:
    tgt = loaded.manifest.target
    ce = tgt.connection_env
    host_kind = env.get("LDM_HOST", "local")
    if tgt.provider == "postgresql":
        return TargetSpec("postgresql", _postgres_kwargs(loaded, env, host_kind))
    if tgt.provider == "snowflake":
        assert tgt.archive is not None
        ae = tgt.archive.connection_env
        require_env(
            dict(env), [ae.account, ae.user, ae.token, ae.role, ae.warehouse, ae.database], "target snowflake archive"
        )
        stage = env.get(ae.stage) if ae.stage else None
        return TargetSpec(
            "snowflake",
            {
                "control": _postgres_kwargs(loaded, env, host_kind),
                "archive": {
                    "account": env[ae.account],
                    "user": env[ae.user],
                    "token": env[ae.token],
                    "role": env[ae.role],
                    "warehouse": env[ae.warehouse],
                    "database": env[ae.database],
                    "stage": stage or "STG.LDM_STAGE",
                },
            },
        )
    if tgt.provider == "azuresql":
        assert ce.server and ce.auth_mode and ce.managed_identity_client_id
        auth = env.get(ce.auth_mode) or "sql"
        require_env(dict(env), [ce.server, ce.database], "target azuresql")
        if auth == "sql":
            require_env(dict(env), [ce.user, ce.password], f"target azuresql ({ce.auth_mode}=sql)")
        elif auth == "managed-identity":
            require_env(
                dict(env), [ce.managed_identity_client_id], f"target azuresql ({ce.auth_mode}=managed-identity)"
            )
        else:
            raise ConfigError(f"{ce.auth_mode}={auth!r}: expected 'sql' or 'managed-identity'")
        return TargetSpec(
            "azuresql",
            {
                "server": env[ce.server],
                "database": env[ce.database],
                "auth": auth,
                "user": env.get(ce.user),
                "password": env.get(ce.password),
                "client_id": env.get(ce.managed_identity_client_id),
                "host": host_kind,
            },
        )
    raise ConfigError(f"target.provider {tgt.provider!r} has no driver in this build")
