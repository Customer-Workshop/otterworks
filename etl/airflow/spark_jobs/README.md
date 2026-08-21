# Spark jobs

PySpark applications submitted by the DAGs with
`SparkSubmitOperator(conn_id="spark_default", application=...)`.

Contract:

* one file per pipeline, named after the DAG it belongs to
  (`analytics_aggregate.py` for `otterworks_analytics_etl`);
* the application path is built from the Variable
  `otterworks_spark_jobs_path` (this directory as deployed on the workers),
  never hardcoded;
* the job takes explicit `--input`/`--output`/`--ds` arguments — no
  `datetime.now()` inside the job — and writes with `mode="overwrite"` to a
  `ds`-partitioned path so a re-run replaces its own partition;
* the aggregation logic is a module-level function taking and returning a
  Spark `DataFrame`, so it can be exercised directly;
* the module must be importable without a cluster: build the `SparkSession`
  inside `main()`, guarded by `if __name__ == "__main__":`.

## Testing without a cluster

`tests/conftest.py` provides a session-scoped `spark_session` fixture: a local
`master("local[1]")` session with Hive support disabled. Mark such tests with
`@pytest.mark.spark`.

Spark 3.5 does not support Java 21 — the fixture selects a Java 17 JDK if one
is installed and fails the test loudly otherwise, rather than skipping (CI
provisions Temurin 17). Run just these tests with:

```bash
./check.sh test -m spark
```
