"""Snowflake archive store behind the PostgreSQL control plane (target.provider snowflake).

The target is split in two (SNOWFLAKE-PORT-SPEC.md §3): the tenant's PostgreSQL database keeps every transactional
control table (mig.runs, run_ledger, key_ranges, rejects, validation, class_totals, purge_audit, stage_log), while
Snowflake holds the bulk data: STG.<table> (this run's converted rows), ARCH.<table> (served archive) and a mirror
of the verdicts (MIG.VALIDATION, MIG.RUNS, MIG.RUN_LEDGER) so promotion and the reporting views are set-based inside
Snowflake. Staged rows travel as Parquet: one file per insert_staging batch is PUT to an internal stage and loaded
with COPY INTO (FORCE so a restarted range reloads, PURGE so the stage never accumulates).

Duplicate source keys (MIG-06) are a real constraint on PostgreSQL but not on Snowflake, so after each COPY the
batch is checked against rows of the same namespace loaded by another run; the losers are removed again and
reported as InsertFailure(sqlstate 23505), which stages.load turns into the DUPLICATE_SOURCE_KEY reject exactly as
for PostgreSQL. Every Snowflake error surfaces as TargetError(sqlstate, errno, text).
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType

from ..convert import Timestamp12
from ..errors import ConfigError, TargetError
from ..typemap import ColumnSpec
from .base import (
    ClassAggregate,
    ClassTotalRow,
    FailureRow,
    InsertFailure,
    KeyRange,
    LedgerRow,
    PurgeAuditRow,
    Reject,
    StagedRow,
    TargetValue,
    ValidationRow,
)
from .postgresql import PostgresTarget, join_timestamp12, split_timestamp12

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,254}$")
_NAMESPACE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
DEFAULT_STAGE = "STG.LDM_STAGE"
DUPLICATE_SQLSTATE = "23505"
MIG_MIRROR_TABLES = ("VALIDATION", "RUN_LEDGER", "RUNS", "SCHEMA_VERSION")


def parse_sf_error(exc: BaseException) -> tuple[str | None, int | None, str]:
    """(sqlstate, Snowflake error number, text) from a snowflake.connector.errors.Error."""
    sqlstate = getattr(exc, "sqlstate", None)
    errno = getattr(exc, "errno", None)
    msg = getattr(exc, "raw_msg", None) or getattr(exc, "msg", None) or str(exc)
    return (str(sqlstate) if sqlstate else None), (int(errno) if errno else None), str(msg)


def _ident(name: str) -> str:
    if not _IDENT_RE.match(name):
        raise ConfigError(f"unsafe SQL identifier {name!r}")
    return name.upper()


def _namespace_literal(namespace: str) -> str:
    if not _NAMESPACE_RE.match(namespace):
        raise ConfigError(f"unsafe namespace {namespace!r}")
    return f"'{namespace}'"


@dataclass
class _Shape:
    key_columns: tuple[str, ...]
    hash_columns: tuple[str, ...]
    specs: list[ColumnSpec]

    @property
    def target_columns(self) -> list[str]:
        return [c for s in self.specs for c in s.target_columns]


class SnowflakeArchive:
    """The Snowflake half of the split target: STG/ARCH tables, the MIG mirror, Parquet COPY INTO."""

    def __init__(
        self,
        account: str,
        user: str,
        token: str,
        role: str,
        warehouse: str,
        database: str,
        *,
        stage: str = DEFAULT_STAGE,
        connect_timeout: int = 60,
    ):
        self.account, self.user, self.token = account, user, token
        self.role, self.warehouse = _ident(role), _ident(warehouse)
        self.database = _ident(database)
        schema, _, name = stage.rpartition(".")
        self.stage = f"{_ident(schema or 'STG')}.{_ident(name)}"
        self.connect_timeout = connect_timeout
        self._sf: ModuleType | None = None
        self._conn: object | None = None
        self.shapes: dict[str, _Shape] = {}

    # --- connection -------------------------------------------------------------------------------------------------

    @property
    def sf(self) -> ModuleType:
        if self._sf is None:
            try:
                import snowflake.connector
            except ImportError as e:  # pragma: no cover - exercised only without the snowflake extra
                raise ConfigError("snowflake-connector-python is not installed; pip install 'ldm[snowflake]'") from e
            self._sf = snowflake.connector
        return self._sf

    def connect(self) -> None:
        if self._conn is not None:
            return
        try:
            self._conn = self.sf.connect(
                account=self.account,
                user=self.user,
                authenticator="PROGRAMMATIC_ACCESS_TOKEN",
                token=self.token,
                role=self.role,
                warehouse=self.warehouse,
                paramstyle="qmark",
                autocommit=True,
                login_timeout=self.connect_timeout,
                network_timeout=600,
                client_session_keep_alive=False,
                application="ldm",
                session_parameters={"QUERY_TAG": "ldm", "TIMEZONE": "UTC"},
            )
        except self.sf.errors.Error as e:
            raise TargetError(*parse_sf_error(e)) from e

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()  # type: ignore[attr-defined]
            self._conn = None

    @property
    def conn(self) -> object:
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        return self._conn

    def _exec(self, sql: str, params: Sequence[object] = ()) -> object:
        try:
            cur = self.conn.cursor()  # type: ignore[attr-defined]
            cur.execute(sql, list(params) if params else None)
            return cur
        except self.sf.errors.Error as e:
            raise TargetError(*parse_sf_error(e)) from e

    def _run(self, sql: str, params: Sequence[object] = ()) -> int:
        cur = self._exec(sql, params)
        n = cur.rowcount  # type: ignore[attr-defined]
        cur.close()  # type: ignore[attr-defined]
        return int(n) if n is not None else 0

    def _rows(self, sql: str, params: Sequence[object] = ()) -> list[tuple[object, ...]]:
        cur = self._exec(sql, params)
        try:
            return [tuple(r) for r in cur.fetchall()]  # type: ignore[attr-defined]
        finally:
            cur.close()  # type: ignore[attr-defined]

    def _scalar(self, sql: str, params: Sequence[object] = ()) -> object:
        rows = self._rows(sql, params)
        return rows[0][0] if rows else None

    def _executemany(self, sql: str, rows: Sequence[Sequence[object]]) -> None:
        if not rows:
            return
        try:
            with self.conn.cursor() as cur:  # type: ignore[attr-defined]
                cur.executemany(sql, [list(r) for r in rows])
        except self.sf.errors.Error as e:
            raise TargetError(*parse_sf_error(e)) from e

    def _script(self, sql_text: str) -> None:
        try:
            self.conn.execute_string(sql_text, return_cursors=False)  # type: ignore[attr-defined]
        except self.sf.errors.Error as e:
            raise TargetError(*parse_sf_error(e)) from e

    def _q(self, schema: str, name: str) -> str:
        return f"{self.database}.{_ident(schema)}.{_ident(name)}"

    def register_table(
        self, table: str, key_columns: Sequence[str], hash_columns: Sequence[str], specs: list[ColumnSpec]
    ) -> None:
        self.shapes[table] = _Shape(tuple(key_columns), tuple(hash_columns), specs)

    def _shape(self, table: str) -> _Shape:
        if table not in self.shapes:
            raise ConfigError(f"table {table} was not registered with the target driver")
        return self.shapes[table]

    # --- init -------------------------------------------------------------------------------------------------------

    def ensure_database(self) -> None:
        """The tenant database normally pre-exists (bootstrap/tenant.sql, owned by the job role); creating it here
        is the local / ad-hoc path and needs CREATE DATABASE on the account."""
        if self._rows(f"SHOW DATABASES LIKE '{self.database.strip(chr(34))}'"):
            return
        self._run(f"CREATE DATABASE IF NOT EXISTS {self.database}")

    def _table_exists(self, schema: str, name: str) -> bool:
        v = self._scalar(
            f"SELECT COUNT(*) FROM {self.database}.INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?",
            (_ident(schema), _ident(name)),
        )
        return bool(v)

    def applied_ddl(self) -> dict[str, str]:
        self.ensure_database()
        if not self._table_exists("MIG", "SCHEMA_VERSION"):
            return {}
        return {
            str(f): str(s).strip()
            for f, s in self._rows(f"SELECT FILE_NAME, FILE_SHA256 FROM {self._q('MIG', 'SCHEMA_VERSION')}")
        }

    def apply_ddl(self, sql_text: str, file_name: str, sha256_hex: str) -> None:
        self.ensure_database()
        self._script(f"USE DATABASE {self.database};\n{sql_text}")
        self._run(
            f"MERGE INTO {self._q('MIG', 'SCHEMA_VERSION')} t USING (SELECT ? AS FILE_NAME, ? AS FILE_SHA256) s "
            "ON t.FILE_NAME = s.FILE_NAME "
            "WHEN MATCHED THEN UPDATE SET FILE_SHA256 = s.FILE_SHA256, APPLIED_AT = SYSDATE()::TIMESTAMP_NTZ(3) "
            "WHEN NOT MATCHED THEN INSERT (FILE_NAME, FILE_SHA256) VALUES (s.FILE_NAME, s.FILE_SHA256)",
            (file_name, sha256_hex),
        )

    def apply_sql_in_namespace(self, sql_text: str, namespace: str) -> None:
        """Run a fixture script with $LDM_NAMESPACE bound (the Snowflake spelling of PostgreSQL's ldm.namespace)."""
        self._script(f"USE DATABASE {self.database};\nSET LDM_NAMESPACE = {_namespace_literal(namespace)};\n{sql_text}")

    # --- staging ----------------------------------------------------------------------------------------------------

    def delete_staging_range(self, run_id: str, namespace: str, table: str, range_seq: int) -> None:
        self._run(
            f"DELETE FROM {self._q('STG', table)} WHERE RUN_ID = ? AND NAMESPACE = ? AND RANGE_SEQ = ?",
            (run_id, namespace, range_seq),
        )

    def delete_staging_run(self, run_id: str, namespace: str) -> None:
        for table in self.shapes:
            self._run(f"DELETE FROM {self._q('STG', table)} WHERE RUN_ID = ? AND NAMESPACE = ?", (run_id, namespace))

    def count_staging(self, run_id: str, namespace: str, table: str) -> int:
        v = self._scalar(
            f"SELECT COUNT(*) FROM {self._q('STG', table)} WHERE RUN_ID = ? AND NAMESPACE = ?", (run_id, namespace)
        )
        return int(v)  # type: ignore[call-overload]

    def _arrow_schema(self, shape: _Shape) -> object:
        import pyarrow as pa

        fields = [
            pa.field("RUN_ID", pa.string()),
            pa.field("NAMESPACE", pa.string()),
            pa.field("SOURCE_KEY", pa.string()),
            pa.field("RANGE_SEQ", pa.int32()),
            pa.field("BATCH_ID", pa.int64()),
            pa.field("RAW_BYTES", pa.binary()),
            pa.field("LOADED_AT", pa.timestamp("us")),
        ]
        for spec in shape.specs:
            if spec.kind == "char":
                fields.append(pa.field(spec.name, pa.string()))
            elif spec.kind == "int":
                fields.append(pa.field(spec.name, pa.int64()))
            elif spec.kind == "decimal":
                fields.append(pa.field(spec.name, pa.decimal128(int(spec.target_precision), int(spec.target_scale))))
            elif spec.kind == "timestamp12":
                fields.append(pa.field(spec.name, pa.timestamp("us")))
                fields.append(pa.field(f"{spec.name}_NANOS_TAIL", pa.int32()))
            elif spec.kind == "date8":
                fields.append(pa.field(spec.name, pa.date32()))
            else:
                fields.append(pa.field(spec.name, pa.binary()))
        return pa.schema(fields)

    @staticmethod
    def _column_values(rows: Sequence[StagedRow], spec: ColumnSpec) -> tuple[list[object], list[object]]:
        """Values of one spec across `rows` (the second list is the nanos tail of a timestamp12 column)."""
        col: list[object] = []
        tail: list[object] = []
        for row in rows:
            v = row.values[spec.name]
            if spec.kind == "timestamp12":
                if isinstance(v, Timestamp12):
                    dt, t6 = split_timestamp12(v)
                    col.append(dt)
                    tail.append(t6)
                else:
                    col.append(v)
                    tail.append(row.values.get(f"{spec.name}_NANOS_TAIL"))
            elif spec.kind == "decimal" and isinstance(v, Decimal):
                col.append(v.quantize(Decimal(1).scaleb(-int(spec.target_scale))))
            elif spec.kind == "decimal" and v is not None:
                col.append(Decimal(str(v)).quantize(Decimal(1).scaleb(-int(spec.target_scale))))
            else:
                col.append(v)
        return col, tail

    def _write_parquet(
        self, path: Path, run_id: str, namespace: str, shape: _Shape, rows: Sequence[StagedRow], batch_id: int
    ) -> None:
        import pyarrow as pa
        import pyarrow.parquet as pq

        now = datetime.now(UTC).replace(tzinfo=None)
        columns: dict[str, list[object]] = {
            "RUN_ID": [run_id] * len(rows),
            "NAMESPACE": [namespace] * len(rows),
            "SOURCE_KEY": [r.source_key for r in rows],
            "RANGE_SEQ": [r.key_range_seq if r.key_range_seq is not None else 0 for r in rows],
            "BATCH_ID": [batch_id] * len(rows),
            "RAW_BYTES": [r.raw_bytes for r in rows],
            "LOADED_AT": [now] * len(rows),
        }
        for spec in shape.specs:
            col, tail = self._column_values(rows, spec)
            columns[spec.name] = col
            if spec.kind == "timestamp12":
                columns[f"{spec.name}_NANOS_TAIL"] = tail
        schema = self._arrow_schema(shape)
        table = pa.Table.from_pydict(columns, schema=schema)  # type: ignore[arg-type]
        pq.write_table(table, path, compression="snappy")

    def _put(self, local: Path, stage_dir: str) -> None:
        self._run(
            f"PUT 'file://{local.as_posix()}' '@{self.database}.{self.stage}/{stage_dir}' "
            "AUTO_COMPRESS=FALSE OVERWRITE=TRUE PARALLEL=4"
        )

    def _copy(self, schema: str, table: str, stage_dir: str, file_name: str) -> int:
        rows = self._rows(
            f"COPY INTO {self._q(schema, table)} FROM '@{self.database}.{self.stage}/{stage_dir}/' "
            f"FILES = ('{file_name}') FILE_FORMAT = (TYPE = PARQUET USE_LOGICAL_TYPE = TRUE BINARY_AS_TEXT = FALSE) "
            "MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE ON_ERROR = ABORT_STATEMENT FORCE = TRUE PURGE = TRUE"
        )
        loaded = 0
        for r in rows:
            status = str(r[1]) if len(r) > 1 else ""
            if status.upper() not in ("LOADED", "LOAD_SKIPPED"):
                raise TargetError(None, None, f"COPY INTO {schema}.{table}: {status}: {r[6] if len(r) > 6 else r}")
            loaded += int(r[3]) if len(r) > 3 and r[3] is not None else 0  # type: ignore[call-overload]
        return loaded

    def _copy_rows(self, run_id: str, namespace: str, table: str, shape: _Shape, rows: Sequence[StagedRow]) -> int:
        """Parquet -> PUT -> COPY INTO STG.<table> for one batch. Returns the BATCH_ID stamped on the rows."""
        batch_id = int(time.time_ns() // 1000) ^ (uuid.uuid4().int & 0xFFFF)
        stage_dir = f"{run_id}/{table}"
        file_name = f"{namespace}-{batch_id}.parquet"
        with TemporaryDirectory(prefix="ldm-sf-") as tmp:
            local = Path(tmp) / file_name
            self._write_parquet(local, run_id, namespace, shape, rows, batch_id)
            self._put(local, stage_dir)
        loaded = self._copy("STG", table, stage_dir, file_name)
        if loaded != len(rows):
            raise TargetError(None, None, f"COPY INTO STG.{table} loaded {loaded} of {len(rows)} rows")
        return batch_id

    def _reject_duplicates(self, run_id: str, namespace: str, table: str, batch_id: int) -> list[InsertFailure]:
        """Rows of this batch whose (namespace, source_key) another run already staged lose, as with the
        PostgreSQL unique index: they are removed again and reported with SQLSTATE 23505."""
        stg = self._q("STG", table)
        where = (
            f"FROM {stg} s WHERE s.RUN_ID = ? AND s.NAMESPACE = ? AND s.BATCH_ID = ? AND EXISTS ("
            f"SELECT 1 FROM {stg} o WHERE o.NAMESPACE = s.NAMESPACE AND o.SOURCE_KEY = s.SOURCE_KEY "
            "AND o.RUN_ID <> s.RUN_ID)"
        )
        params = (run_id, namespace, batch_id)
        keys = [str(r[0]) for r in self._rows(f"SELECT s.SOURCE_KEY {where}", params)]
        if not keys:
            return []
        self._run(f"DELETE {where}", params)
        return [
            InsertFailure(k, DUPLICATE_SQLSTATE, None, f"duplicate key value violates unique index on STG.{table}")
            for k in keys
        ]

    def insert_staging(self, run_id: str, namespace: str, table: str, rows: Sequence[StagedRow]) -> list[InsertFailure]:
        if not rows:
            return []
        shape = self._shape(table)
        failures: list[InsertFailure] = []
        self._copy_bisect(run_id, namespace, table, shape, list(rows), failures)
        return failures

    def _copy_bisect(
        self,
        run_id: str,
        namespace: str,
        table: str,
        shape: _Shape,
        rows: list[StagedRow],
        failures: list[InsertFailure],
    ) -> None:
        try:
            batch_id = self._copy_rows(run_id, namespace, table, shape, rows)
        except TargetError as e:
            if len(rows) == 1:
                text = e.text.replace("\x00", "\\x00")  # Snowflake echoes the record; the ledger is PostgreSQL text
                failures.append(InsertFailure(rows[0].source_key, e.sqlstate, e.native_error, text))
                return
            mid = len(rows) // 2
            self._copy_bisect(run_id, namespace, table, shape, rows[:mid], failures)
            self._copy_bisect(run_id, namespace, table, shape, rows[mid:], failures)
            return
        failures.extend(self._reject_duplicates(run_id, namespace, table, batch_id))

    def iter_staging(self, run_id: str, namespace: str, table: str, batch: int) -> Iterator[list[StagedRow]]:
        shape = self._shape(table)
        columns = shape.target_columns
        select = ", ".join(["SOURCE_KEY", "RANGE_SEQ", "RAW_BYTES", *(_ident(c) for c in columns)])
        cur = self._exec(
            f"SELECT {select} FROM {self._q('STG', table)} WHERE RUN_ID = ? AND NAMESPACE = ? ORDER BY SOURCE_KEY",
            (run_id, namespace),
        )
        try:
            while True:
                try:
                    rows = cur.fetchmany(int(batch))  # type: ignore[attr-defined]
                except self.sf.errors.Error as e:
                    raise TargetError(*parse_sf_error(e)) from e
                if not rows:
                    return
                out: list[StagedRow] = []
                for r in rows:
                    values = self._read_row(shape, dict(zip(columns, r[3:], strict=True)))
                    out.append(StagedRow(table, str(r[0]), int(r[1]), bytes(r[2]), values))  # type: ignore[call-overload]
                yield out
        finally:
            cur.close()  # type: ignore[attr-defined]

    @classmethod
    def _read_row(cls, shape: _Shape, raw: dict[str, object]) -> dict[str, TargetValue]:
        values: dict[str, TargetValue] = {}
        for spec in shape.specs:
            v = raw[spec.name]
            if spec.kind == "timestamp12" and isinstance(v, datetime):
                ts = join_timestamp12(v.replace(tzinfo=None), int(raw[f"{spec.name}_NANOS_TAIL"]))  # type: ignore[call-overload]
                values[spec.name] = ts
                values[f"{spec.name}_NANOS_TAIL"] = ts.nanos_tail
            else:
                values[spec.name] = cls._read_value(v, spec)
                if spec.kind == "timestamp12":
                    values[f"{spec.name}_NANOS_TAIL"] = cls._read_value(raw[f"{spec.name}_NANOS_TAIL"], None)
        return values

    @staticmethod
    def _read_value(v: object, spec: ColumnSpec | None) -> TargetValue:
        if v is None:
            return None
        if spec is not None and spec.kind == "int" and isinstance(v, int | Decimal):
            return int(v)
        if isinstance(v, str | int | Decimal | bytes | datetime | date):
            return v
        if isinstance(v, bytearray | memoryview):
            return bytes(v)
        if isinstance(v, bool):
            return int(v)
        return str(v)

    def target_hashes(
        self, run_id: str, namespace: str, table: str, tsql_expr: str, key_from: str, key_to: str
    ) -> dict[str, bytes]:
        rows = self._rows(
            f"SELECT SOURCE_KEY, {tsql_expr} FROM {self._q('STG', table)} WHERE RUN_ID = ? AND NAMESPACE = ? "
            "AND SOURCE_KEY >= ? AND SOURCE_KEY <= ?",
            (run_id, namespace, key_from, key_to),
        )
        return {str(k): bytes(h) for k, h in rows}  # type: ignore[call-overload]

    def class_aggregates(
        self, run_id: str, namespace: str, table: str, class_column: str, sum_columns: Sequence[str]
    ) -> dict[str, ClassAggregate]:
        sums = ", ".join(f"SUM({_ident(c)}::NUMBER(38,8))" for c in sum_columns)
        cls_expr = f"RTRIM({_ident(class_column)}, ' ')"
        sql = (
            f"SELECT {cls_expr}, COUNT(*){', ' + sums if sums else ''} "
            f"FROM {self._q('STG', table)} WHERE RUN_ID = ? AND NAMESPACE = ? GROUP BY {cls_expr}"
        )
        out: dict[str, ClassAggregate] = {}
        for r in self._rows(sql, (run_id, namespace)):
            agg = ClassAggregate(count=int(r[1]))  # type: ignore[call-overload]
            for c, v in zip(sum_columns, r[2:], strict=True):
                agg.sums[c] = Decimal(str(v)) if v is not None else Decimal(0)
            out[str(r[0])] = agg
        return out

    def parents_present(
        self,
        run_id: str,
        namespace: str,
        child_table: str,
        child_columns: Sequence[str],
        parent_table: str,
        parent_columns: Sequence[str],
    ) -> set[str]:
        if len(child_columns) != len(parent_columns):
            raise ValueError("child_columns and parent_columns must have the same length")
        child_key = ", ".join(f"RTRIM(c.{_ident(cc)}, ' ')" for cc in child_columns)
        parent_key = ", ".join(f"RTRIM(p.{_ident(pc)}, ' ')" for pc in parent_columns)
        sql = (
            f"SELECT c.SOURCE_KEY FROM {self._q('STG', child_table)} c WHERE c.RUN_ID = ? AND c.NAMESPACE = ? "
            f"AND ({child_key}) IN ("
            f"SELECT {parent_key} FROM {self._q('STG', parent_table)} p JOIN {self._q('MIG', 'VALIDATION')} v "
            "ON v.RUN_ID = p.RUN_ID AND v.NAMESPACE = p.NAMESPACE AND v.TABLE_NAME = ? "
            "AND v.SOURCE_KEY = p.SOURCE_KEY AND v.STATUS = 'VALIDATED' "
            "WHERE p.RUN_ID = ? AND p.NAMESPACE = ? "
            "UNION ALL "
            f"SELECT {parent_key} FROM {self._q('ARCH', parent_table)} p WHERE p.NAMESPACE = ?)"
        )
        params = (run_id, namespace, parent_table, run_id, namespace, namespace)
        return {str(r[0]) for r in self._rows(sql, params)}

    def archived_hashes(self, run_id: str, namespace: str, table: str, key_columns: Sequence[str]) -> dict[str, bytes]:
        key_match = " AND ".join(f"a.{_ident(k)} = s.{_ident(k)}" for k in key_columns)
        rows = self._rows(
            f"SELECT s.SOURCE_KEY, a.ROW_HASH FROM {self._q('STG', table)} s JOIN {self._q('ARCH', table)} a "
            f"ON a.NAMESPACE = s.NAMESPACE AND {key_match} WHERE s.RUN_ID = ? AND s.NAMESPACE = ?",
            (run_id, namespace),
        )
        return {str(k): bytes(h) for k, h in rows}  # type: ignore[call-overload]

    # --- verdict mirror + promotion ---------------------------------------------------------------------------------

    def mirror_validation(self, run_id: str, namespace: str, table: str, rows: Sequence[ValidationRow]) -> None:
        """Replace this table's MIG.VALIDATION rows for the run with the control plane's verdicts."""
        self._run(
            f"DELETE FROM {self._q('MIG', 'VALIDATION')} WHERE RUN_ID = ? AND NAMESPACE = ? AND TABLE_NAME = ?",
            (run_id, namespace, table),
        )
        self._executemany(
            f"INSERT INTO {self._q('MIG', 'VALIDATION')} (RUN_ID, NAMESPACE, TABLE_NAME, SOURCE_KEY, SOURCE_HASH, "
            "TARGET_HASH, STATUS, RULE_NAME, PURGE_SAFE) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    run_id,
                    namespace,
                    table,
                    r.source_key,
                    r.source_hash if r.source_hash is not None else bytes(32),
                    r.target_hash,
                    r.status,
                    r.rule,
                    r.purge_safe,
                )
                for r in rows
            ],
        )

    def promote(self, run_id: str, namespace: str, table: str, key_columns: Sequence[str]) -> int:
        columns = self._shape(table).target_columns
        cols = ", ".join(_ident(c) for c in columns)
        s_cols = ", ".join("s." + _ident(c) for c in columns)
        key_match = " AND ".join(f"a.{_ident(k)} = s.{_ident(k)}" for k in key_columns)
        arch, stg, val = self._q("ARCH", table), self._q("STG", table), self._q("MIG", "VALIDATION")
        n = self._run(
            f"INSERT INTO {arch} ({cols}, SOURCE_KEY, ROW_HASH, NAMESPACE, MIGRATED_RUN_ID) "
            f"SELECT {s_cols}, s.SOURCE_KEY, v.SOURCE_HASH, s.NAMESPACE, s.RUN_ID "
            f"FROM {stg} s JOIN {val} v ON v.RUN_ID = s.RUN_ID "
            "AND v.NAMESPACE = s.NAMESPACE AND v.TABLE_NAME = ? AND v.SOURCE_KEY = s.SOURCE_KEY "
            "AND v.STATUS = 'VALIDATED' WHERE s.RUN_ID = ? AND s.NAMESPACE = ? "
            f"AND NOT EXISTS (SELECT 1 FROM {arch} a WHERE a.NAMESPACE = s.NAMESPACE AND {key_match})",
            (table, run_id, namespace),
        )
        return max(n, 0)

    def mirror_run(
        self,
        run_id: str,
        namespace: str,
        status: str,
        purge_enabled: bool | None,
        exit_code: int | None,
        ledger: Sequence[LedgerRow],
    ) -> None:
        """Copy the closed run's header and ledger so MIG.V_RUN_SUMMARY reads inside Snowflake."""
        self._run(f"DELETE FROM {self._q('MIG', 'RUN_LEDGER')} WHERE RUN_ID = ? AND NAMESPACE = ?", (run_id, namespace))
        self._run(f"DELETE FROM {self._q('MIG', 'RUNS')} WHERE RUN_ID = ? AND NAMESPACE = ?", (run_id, namespace))
        self._run(
            f"INSERT INTO {self._q('MIG', 'RUNS')} (RUN_ID, NAMESPACE, STATUS, PURGE_ENABLED, EXIT_CODE, CLOSES, "
            "FINISHED_AT) VALUES (?, ?, ?, ?, ?, ?, SYSDATE()::TIMESTAMP_NTZ(3))",
            (run_id, namespace, status, purge_enabled, exit_code, status == "CLOSED"),
        )
        self._executemany(
            f"INSERT INTO {self._q('MIG', 'RUN_LEDGER')} (RUN_ID, NAMESPACE, TABLE_NAME, TABLE_ORDER, TABLE_ROLE, "
            "EXTRACTED, EXTRACT_FILES, LOADED, REJECTED, VALIDATED, VALIDATE_FAILED, PURGE_INTENDED, PURGED, "
            "PURGE_DRY_RUN) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    run_id,
                    namespace,
                    r.table_name,
                    r.table_order,
                    r.table_role,
                    r.extracted,
                    r.extract_files,
                    r.loaded,
                    r.rejected,
                    r.validated,
                    r.validate_failed,
                    r.purge_intended,
                    r.purged,
                    r.purge_dry_run,
                )
                for r in ledger
            ],
        )

    # --- teardown ---------------------------------------------------------------------------------------------------

    def drop_namespace(self, namespace: str) -> dict[str, int]:
        """Delete every row this namespace wrote to Snowflake (archive, staging, verdict mirror)."""
        if not self._table_exists("MIG", "RUNS"):
            return {}
        deleted: dict[str, int] = {}
        for table in reversed(list(self.shapes)):
            for schema in ("ARCH", "STG"):
                deleted[f"{schema}.{table}"] = self._run(
                    f"DELETE FROM {self._q(schema, table)} WHERE NAMESPACE = ?", (namespace,)
                )
        for table in ("VALIDATION", "RUN_LEDGER", "RUNS"):
            deleted[f"MIG.{table}"] = self._run(
                f"DELETE FROM {self._q('MIG', table)} WHERE NAMESPACE = ?", (namespace,)
            )
        return deleted


class SnowflakeTarget:
    """TargetDriver = PostgreSQL control plane + SnowflakeArchive bulk store (SNOWFLAKE-PORT-SPEC.md §3).

    Every control-table method delegates to the PostgreSQL driver unchanged (same ledger, checkpoints, rejects,
    purge audit, reconciliation views); staging/archive methods go to Snowflake; the two verdict-carrying methods
    (promote, set_run_status) write PostgreSQL first and then mirror into Snowflake.
    """

    def __init__(self, control: PostgresTarget, archive: SnowflakeArchive):
        self.control = control
        self.archive = archive

    @property
    def host(self) -> str:
        return self.control.host

    @property
    def database(self) -> str:
        return self.control.database

    def connect(self) -> None:
        self.control.connect()
        self.archive.connect()

    def close(self) -> None:
        self.archive.close()
        self.control.close()

    def register_table(
        self, table: str, key_columns: Sequence[str], hash_columns: Sequence[str], specs: list[ColumnSpec]
    ) -> None:
        self.control.register_table(table, key_columns, hash_columns, specs)
        self.archive.register_table(table, key_columns, hash_columns, specs)

    # --- init: control plane DDL, archive DDL -----------------------------------------------------------------------

    def applied_ddl(self) -> dict[str, str]:
        return self.control.applied_ddl()

    def apply_ddl(self, sql_text: str, file_name: str, sha256_hex: str) -> None:
        self.control.apply_ddl(sql_text, file_name, sha256_hex)

    def applied_archive_ddl(self) -> dict[str, str]:
        return self.archive.applied_ddl()

    def apply_archive_ddl(self, sql_text: str, file_name: str, sha256_hex: str) -> None:
        self.archive.apply_ddl(sql_text, file_name, sha256_hex)

    def ensure_reader(self, user: str, password: str) -> None:
        self.control.ensure_reader(user, password)

    def apply_sql_in_namespace(self, sql_text: str, namespace: str) -> None:
        self.control.apply_sql_in_namespace(sql_text, namespace)

    def apply_archive_sql_in_namespace(self, sql_text: str, namespace: str) -> None:
        self.archive.apply_sql_in_namespace(sql_text, namespace)

    # --- run / ledger / stage log (PostgreSQL) ----------------------------------------------------------------------

    def ensure_run(
        self, run_id: str, namespace: str, purge_enabled: bool, job_image: str | None, manifest_sha: str
    ) -> str:
        return self.control.ensure_run(run_id, namespace, purge_enabled, job_image, manifest_sha)

    def refresh_run(self, run_id: str, namespace: str, purge_enabled: bool, job_image: str | None) -> None:
        self.control.refresh_run(run_id, namespace, purge_enabled, job_image)

    def get_run_status(self, run_id: str, namespace: str) -> str | None:
        return self.control.get_run_status(run_id, namespace)

    def set_run_status(self, run_id: str, namespace: str, status: str, exit_code: int | None) -> None:
        self.control.set_run_status(run_id, namespace, status, exit_code)
        if status == "RUNNING":
            return
        ledger = list(self.control.get_ledger(run_id, namespace).values())
        self.archive.mirror_run(
            run_id, namespace, status, self.control.run_purge_enabled(run_id, namespace), exit_code, ledger
        )

    def ensure_ledger(self, run_id: str, namespace: str, tables: Sequence[tuple[str, int, str]]) -> None:
        self.control.ensure_ledger(run_id, namespace, tables)

    def get_ledger(self, run_id: str, namespace: str) -> dict[str, LedgerRow]:
        return self.control.get_ledger(run_id, namespace)

    def update_ledger(self, run_id: str, namespace: str, table: str, **cols: int | bool | None) -> None:
        self.control.update_ledger(run_id, namespace, table, **cols)

    def stage_log_start(self, run_id: str, namespace: str, stage: str, table: str | None) -> int:
        return self.control.stage_log_start(run_id, namespace, stage, table)

    def stage_log_finish(self, log_id: int, status: str, rows: int | None, message: str | None) -> None:
        self.control.stage_log_finish(log_id, status, rows, message)

    # --- key ranges / rejects (PostgreSQL) --------------------------------------------------------------------------

    def get_key_ranges(self, run_id: str, namespace: str, table: str) -> list[KeyRange]:
        return self.control.get_key_ranges(run_id, namespace, table)

    def insert_key_ranges(self, run_id: str, namespace: str, ranges: Sequence[KeyRange]) -> None:
        self.control.insert_key_ranges(run_id, namespace, ranges)

    def update_key_range(self, run_id: str, namespace: str, table: str, range_seq: int, **cols: object) -> None:
        self.control.update_key_range(run_id, namespace, table, range_seq, **cols)

    def insert_rejects(self, run_id: str, namespace: str, rejects: Sequence[Reject]) -> None:
        self.control.insert_rejects(run_id, namespace, rejects)

    def count_rejects(self, run_id: str, namespace: str, table: str, stage: str | None = None) -> int:
        return self.control.count_rejects(run_id, namespace, table, stage)

    def delete_rejects_keys(self, run_id: str, namespace: str, table: str, stage: str, keys: Sequence[str]) -> None:
        self.control.delete_rejects_keys(run_id, namespace, table, stage, keys)

    def delete_rejects_range(self, run_id: str, namespace: str, table: str, stage: str, range_seq: int) -> None:
        self.control.delete_rejects_range(run_id, namespace, table, stage, range_seq)

    # --- staging / archive (Snowflake) ------------------------------------------------------------------------------

    def delete_staging_range(self, run_id: str, namespace: str, table: str, range_seq: int) -> None:
        self.archive.delete_staging_range(run_id, namespace, table, range_seq)

    def insert_staging(self, run_id: str, namespace: str, table: str, rows: Sequence[StagedRow]) -> list[InsertFailure]:
        return self.archive.insert_staging(run_id, namespace, table, rows)

    def count_staging(self, run_id: str, namespace: str, table: str) -> int:
        return self.archive.count_staging(run_id, namespace, table)

    def iter_staging(self, run_id: str, namespace: str, table: str, batch: int) -> Iterator[list[StagedRow]]:
        return self.archive.iter_staging(run_id, namespace, table, batch)

    def target_hashes(
        self, run_id: str, namespace: str, table: str, tsql_expr: str, key_from: str, key_to: str
    ) -> dict[str, bytes]:
        return self.archive.target_hashes(run_id, namespace, table, tsql_expr, key_from, key_to)

    def class_aggregates(
        self, run_id: str, namespace: str, table: str, class_column: str, sum_columns: Sequence[str]
    ) -> dict[str, ClassAggregate]:
        return self.archive.class_aggregates(run_id, namespace, table, class_column, sum_columns)

    def parents_present(
        self,
        run_id: str,
        namespace: str,
        child_table: str,
        child_columns: Sequence[str],
        parent_table: str,
        parent_columns: Sequence[str],
    ) -> set[str]:
        return self.archive.parents_present(run_id, namespace, child_table, child_columns, parent_table, parent_columns)

    def archived_hashes(self, run_id: str, namespace: str, table: str, key_columns: Sequence[str]) -> dict[str, bytes]:
        return self.archive.archived_hashes(run_id, namespace, table, key_columns)

    def promote(self, run_id: str, namespace: str, table: str, key_columns: Sequence[str]) -> int:
        self.archive.mirror_validation(run_id, namespace, table, self.control.validation_rows(run_id, namespace, table))
        return self.archive.promote(run_id, namespace, table, key_columns)

    def delete_staging_run(self, run_id: str, namespace: str) -> None:
        self.archive.delete_staging_run(run_id, namespace)

    # --- validation verdicts / class totals / purge audit / reconcile (PostgreSQL) -----------------------------------

    def write_validation(self, run_id: str, namespace: str, rows: Sequence[ValidationRow]) -> None:
        self.control.write_validation(run_id, namespace, rows, update_staging_hash=False)

    def write_class_totals(self, run_id: str, namespace: str, rows: Sequence[ClassTotalRow]) -> None:
        self.control.write_class_totals(run_id, namespace, rows)

    def get_class_totals(self, run_id: str, namespace: str) -> list[ClassTotalRow]:
        return self.control.get_class_totals(run_id, namespace)

    def purge_safe_keys(self, run_id: str, namespace: str, table: str) -> list[str]:
        return self.control.purge_safe_keys(run_id, namespace, table)

    def count_validation(self, run_id: str, namespace: str, table: str, status: str) -> int:
        return self.control.count_validation(run_id, namespace, table, status)

    def insert_purge_audit(self, run_id: str, namespace: str, table: str, keys: Sequence[str], batch_no: int) -> None:
        self.control.insert_purge_audit(run_id, namespace, table, keys, batch_no)

    def set_purge_audit_status(self, run_id: str, namespace: str, table: str, keys: Sequence[str], status: str) -> None:
        self.control.set_purge_audit_status(run_id, namespace, table, keys, status)

    def purged_keys(self, run_id: str, namespace: str, table: str) -> set[str]:
        return self.control.purged_keys(run_id, namespace, table)

    def purge_audit_rows(self, run_id: str, namespace: str, table: str) -> list[PurgeAuditRow]:
        return self.control.purge_audit_rows(run_id, namespace, table)

    def failures(self, run_id: str, namespace: str) -> list[FailureRow]:
        return self.control.failures(run_id, namespace)

    def insert_run_sessions(self, run_id: str, namespace: str, sessions: Sequence[tuple[str, str]]) -> None:
        self.control.insert_run_sessions(run_id, namespace, sessions)

    # --- teardown ---------------------------------------------------------------------------------------------------

    def drop_namespace(self, namespace: str) -> dict[str, int]:
        deleted = {f"snowflake:{k}": v for k, v in self.archive.drop_namespace(namespace).items()}
        deleted.update(self.control.drop_namespace(namespace))
        return deleted
