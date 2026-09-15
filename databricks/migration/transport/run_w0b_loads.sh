#!/usr/bin/env bash
# Wave 0, batch w0-b: land the three transport-unit tables through the D-002 JDBC fallback.
# Serial, one live source read per table, well inside the source query cap of 4.
set -euo pipefail
# run from the repository root
#
# customer_master reads in full rather than on a watermark: updated_dt is nullable and
# nothing in the source maintains it, so an update can leave it behind the target's maximum
# and the row would never be read again. invoice_header and invoice_line are append-only
# reporting tables and read in full for the same reason - neither carries a change column.

python3 databricks/migration/recon/with_oracle_secret.py OW_TP_ORACLE_RO ow-tp/oracle/ow_billing_ro -- \
    python3 databricks/migration/transport/jdbc_watermark_load.py --table customer_master --keys cust_id --full-refresh

python3 databricks/migration/recon/with_oracle_secret.py OW_TP_ORACLE_RO ow-tp/oracle/ow_billing_ro -- \
    python3 databricks/migration/transport/jdbc_watermark_load.py --table invoice_header --keys invoice_id

python3 databricks/migration/recon/with_oracle_secret.py OW_TP_ORACLE_RO ow-tp/oracle/ow_billing_ro -- \
    python3 databricks/migration/transport/jdbc_watermark_load.py --table invoice_line --keys line_id
