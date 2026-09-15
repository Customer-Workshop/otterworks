"""One read-only probe that the Oracle JDBC source adapter actually drives the harness.

Wave-0 wiring check only: it counts rows and reads column types through the harness's own
adapter base, so a dialect string that Oracle rejects fails here rather than mid-gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from oracle_jdbc_adapter import OracleJdbcSourceAdapter  # noqa: E402

TABLE = "ow_billing.customer_master"


def main() -> int:
    source = OracleJdbcSourceAdapter("OW_TP_ORACLE_RO")
    print("row_count:", source.row_count(TABLE))
    print("numeric_columns:", sorted(source.numeric_columns(TABLE))[:6])
    print("whole_number_columns:", sorted(source.whole_number_columns(TABLE))[:6])
    agg = source.field_aggregates(TABLE, "cust_id")
    print("cust_id agg keys:", sorted(agg))
    print("statements:", source.statements, "rows_fetched:", source.rows_fetched)
    return 0


if __name__ == "__main__":
    sys.exit(main())
