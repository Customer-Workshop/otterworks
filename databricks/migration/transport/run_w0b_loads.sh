#!/usr/bin/env bash
# Wave 0, batch w0-b: land the three transport-unit tables through the D-002 JDBC fallback.
# Serial, one live source read per table, well inside the source query cap of 4.
set -euo pipefail
# run from the repository root

python3 databricks/migration/recon/with_oracle_secret.py OW_TP_ORACLE_RO ow-tp/oracle/ow_billing_ro -- \
    python3 databricks/migration/transport/jdbc_watermark_load.py --table customer_master --keys cust_id --watermark-column updated_dt

python3 databricks/migration/recon/with_oracle_secret.py OW_TP_ORACLE_RO ow-tp/oracle/ow_billing_ro -- \
    python3 databricks/migration/transport/jdbc_watermark_load.py --table invoice_header --keys invoice_id

python3 databricks/migration/recon/with_oracle_secret.py OW_TP_ORACLE_RO ow-tp/oracle/ow_billing_ro -- \
    python3 databricks/migration/transport/jdbc_watermark_load.py --table invoice_line --keys line_id
