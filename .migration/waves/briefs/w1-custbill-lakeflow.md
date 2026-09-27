UNIT custbill_lakeflow (wave 1, parallel to the package batch; no shared targets). Rebuild the nightly CUSTBILL
chain (etl/legacy-extra: oracle_custbill_extract.py -> ksh/perl fixed-width CUSTBILL_DEMO_ORACLE.dat) as a
Lakeflow Spark Declarative Pipeline with expectations and quarantine. Load databricks:databricks-pipelines,
databricks:databricks-dabs and dbx-migration-factory:target-routing before implementing; read the
legacy-etl-demo skill for the legacy chain.
1. Landing: extract INVOICE_HEADER, INVOICE_LINE, CUSTOMER_MASTER, ENTITY_ATTR_VALUE from Oracle via the session
   bridge (python-oracledb, whole tables, one live read) to parquet and upload to the volume
   /Volumes/ow_tp/mig_20260927b_bronze/custbill_landing/<table>/. No 1521 from serverless, no Debezium.
2. Pipeline ow_tp_20260927b_custbill (DAB under databricks/mig_20260927b/custbill/, target mig_20260927b,
   serverless, schedule PAUSED, never trigger-started): bronze = read_files / Auto Loader of the landing parquet
   into ow_tp.mig_20260927b_bronze.<table> (types per mapping_spec); silver
   ow_tp.mig_20260927b_silver.custbill_records = the legacy extract SQL (batch_no = 85559852 OR
   tenant_id = 'a0000000-0000-0000-0000-000000000001', join customer_master, ordered period_end, cust_no,
   invoice_id) with expectations: cust_no not null, cust_name not null, invoice_dt parses DD-MON-RR, total_amt
   not null and fits 9(10)V99, currency USD. Violations go to ow_tp.mig_20260927b_quarantine.custbill_rejects
   (expect_or_drop plus a quarantine flow; never expect_or_fail on the whole batch).
3. Render job ow_tp_20260927b_custbill_render (serverless python task, schedule PAUSED, run once manually):
   writes the 65-char records (cust_no X(10), cust_name X(30), period_end YYYYMMDD, amount 9(10)V99 implied
   decimal, 'USD', rec_type 01/02, negative -> 02) exactly like format_record() to
   /Volumes/ow_tp/mig_20260927b_bronze/custbill_out/CUSTBILL_DEMO_ORACLE.dat and records the sha256 in the
   one-row table ow_tp.mig_20260927b_silver.custbill_file_manifest (file, bytes, sha256, generated_at).
4. Legacy side: run the legacy chain against Oracle read-only (etl/legacy-extra tools, NS=demo) to produce the
   legacy .dat and its sha256. Gates: w1-cb-structural (pipeline + job exist, both PAUSED),
   w1-cb-bronze-parity (row_parity, depth full, PASS on the 4 bronze tables), w1-cb-file-sha256 (export_file:
   Databricks .dat sha256 == legacy .dat sha256, both hashes and byte counts in
   .migration/recon/custbill_lakeflow/custbill_sha256.json), w1-cb-expectations (pipeline event log shows the
   expectations evaluated; the quarantine table is populated by an injected bad row in a fixture-only run and
   has zero rejects on the live run).
Write targets: ow_tp.mig_20260927b_bronze.{invoice_header, invoice_line, customer_master, entity_attr_value,
custbill_landing (volume), custbill_out (volume)}, ow_tp.mig_20260927b_silver.{custbill_records,
custbill_file_manifest}, ow_tp.mig_20260927b_quarantine.custbill_rejects, pipeline ow_tp_20260927b_custbill,
job ow_tp_20260927b_custbill_render.
