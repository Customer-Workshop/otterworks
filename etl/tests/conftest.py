import configparser
import importlib.util
import subprocess
import time
import uuid
from pathlib import Path

import boto3
import pytest
import requests
from moto import mock_aws


ETL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = ETL_ROOT / "scripts"


@pytest.fixture
def moto_aws(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        yield


@pytest.fixture
def etl_config(tmp_path, monkeypatch):
    values = {
        "access_key": "testing",
        "secret_key": "testing",
        "region": "us-east-1",
        "database_host": "127.0.0.1",
        "database_port": "5432",
        "database": "etl",
        "database_user": "etl",
        "database_password": "postgres",
        "document_service_url": "http://127.0.0.1:1",
        "file_service_url": "http://127.0.0.1:1",
        "meilisearch_url": "http://127.0.0.1:1",
        "meilisearch_api_key": "masterKey",
        "data_lake_bucket": "otterworks-data-lake",
        "file_storage_bucket": "otterworks-file-storage",
        "quarantine_bucket": "otterworks-file-quarantine",
        "archive_bucket": "otterworks-audit-archive",
        "analytics_prefix": "analytics/daily",
    }
    config_path = tmp_path / "config.ini"
    original_read = configparser.ConfigParser.read

    def write_config(**overrides):
        current = {**values, **overrides}
        config_path.write_text(
            "[aws]\n"
            f"access_key = {current['access_key']}\n"
            f"secret_key = {current['secret_key']}\n"
            f"region = {current['region']}\n\n"
            "[database]\n"
            f"host = {current['database_host']}\n"
            f"port = {current['database_port']}\n"
            f"database = {current['database']}\n"
            f"user = {current['database_user']}\n"
            f"password = {current['database_password']}\n\n"
            "[services]\n"
            f"document_service_url = {current['document_service_url']}\n"
            f"file_service_url = {current['file_service_url']}\n"
            f"meilisearch_url = {current['meilisearch_url']}\n"
            f"meilisearch_api_key = {current['meilisearch_api_key']}\n\n"
            "[s3]\n"
            f"data_lake_bucket = {current['data_lake_bucket']}\n"
            f"file_storage_bucket = {current['file_storage_bucket']}\n"
            f"quarantine_bucket = {current['quarantine_bucket']}\n"
            f"archive_bucket = {current['archive_bucket']}\n"
            f"analytics_prefix = {current['analytics_prefix']}\n"
        )

    def redirected_read(parser, filenames, encoding=None):
        return original_read(parser, [str(config_path)], encoding=encoding)

    monkeypatch.setattr(configparser.ConfigParser, "read", redirected_read)
    write_config()
    return write_config


@pytest.fixture
def load_script():
    def load(name):
        path = SCRIPTS_ROOT / name
        module_name = f"etl_script_{path.stem}_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return load


@pytest.fixture
def postgres_service():
    if not _docker_ready():
        reason = "Docker is unavailable; skipping PostgreSQL-dependent ETL tests"
        print(reason)
        pytest.skip(reason)

    name = f"etl-pytest-postgres-{uuid.uuid4().hex[:10]}"
    try:
        _run_docker(
            [
                "run",
                "-d",
                "--name",
                name,
                "-e",
                "POSTGRES_PASSWORD=postgres",
                "-e",
                "POSTGRES_USER=etl",
                "-e",
                "POSTGRES_DB=etl",
                "-p",
                "127.0.0.1::5432",
                "postgres:16",
            ]
        )
        port = _mapped_port(name, "5432/tcp")
        import psycopg2

        deadline = time.monotonic() + 90
        while True:
            try:
                conn = psycopg2.connect(
                    host="127.0.0.1",
                    port=port,
                    dbname="etl",
                    user="etl",
                    password="postgres",
                )
                break
            except psycopg2.OperationalError:
                if time.monotonic() >= deadline:
                    logs = subprocess.run(
                        ["docker", "logs", name],
                        capture_output=True,
                        text=True,
                        check=False,
                    ).stdout[-2000:]
                    pytest.skip(f"PostgreSQL container did not become ready:\n{logs}")
                time.sleep(1)

        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS analytics_daily_summary (
                        report_date DATE PRIMARY KEY,
                        active_users INTEGER NOT NULL,
                        active_documents INTEGER NOT NULL,
                        active_files INTEGER NOT NULL,
                        total_events INTEGER NOT NULL,
                        documents_created INTEGER NOT NULL,
                        documents_edited INTEGER NOT NULL,
                        comments_added INTEGER NOT NULL,
                        files_uploaded INTEGER NOT NULL,
                        files_shared INTEGER NOT NULL,
                        files_deleted INTEGER NOT NULL,
                        bytes_uploaded BIGINT NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
        conn.close()
        yield {"host": "127.0.0.1", "port": port}
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Docker PostgreSQL setup unavailable: {exc}")
        pytest.skip(f"Docker PostgreSQL setup unavailable: {exc}")
    finally:
        subprocess.run(
            ["docker", "rm", "-f", name],
            capture_output=True,
            text=True,
            check=False,
        )


@pytest.fixture
def meilisearch_service():
    if not _docker_ready():
        reason = "Docker is unavailable; skipping MeiliSearch-dependent ETL tests"
        print(reason)
        pytest.skip(reason)

    name = f"etl-pytest-meili-{uuid.uuid4().hex[:10]}"
    try:
        _run_docker(
            [
                "run",
                "-d",
                "--name",
                name,
                "-e",
                "MEILI_MASTER_KEY=masterKey",
                "-p",
                "127.0.0.1::7700",
                "getmeili/meilisearch:v1.15.2",
            ]
        )
        port = _mapped_port(name, "7700/tcp")
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 90
        while True:
            try:
                response = requests.get(f"{url}/health", timeout=2)
                if response.ok:
                    break
            except requests.RequestException:
                pass
            if time.monotonic() >= deadline:
                logs = subprocess.run(
                    ["docker", "logs", name],
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout[-2000:]
                pytest.skip(f"MeiliSearch container did not become ready:\n{logs}")
            time.sleep(1)
        yield {"url": url, "api_key": "masterKey"}
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Docker MeiliSearch setup unavailable: {exc}")
        pytest.skip(f"Docker MeiliSearch setup unavailable: {exc}")
    finally:
        subprocess.run(
            ["docker", "rm", "-f", name],
            capture_output=True,
            text=True,
            check=False,
        )


def _docker_ready():
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _run_docker(args):
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=180, check=True
    )


def _mapped_port(name, container_port):
    result = subprocess.run(
        ["docker", "port", name, container_port],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    return int(result.stdout.strip().rsplit(":", 1)[1])


@pytest.fixture
def http_stub():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import parse_qs, urlparse
    import json
    import threading

    documents = [
        {
            "document_id": f"doc-{i}",
            "title": f"Document {i}",
            "content": "content",
            "owner_id": "owner",
            "tags": ["etl"],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z",
        }
        for i in range(101)
    ]
    files = [
        {
            "file_id": f"file-{i}",
            "file_name": f"file-{i}.txt",
            "owner_id": "owner",
            "mime_type": "text/plain",
            "folder_id": "folder",
            "size_bytes": i,
            "tags": ["etl"],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z",
        }
        for i in range(101)
    ]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path not in ("/api/v1/documents", "/api/v1/files"):
                self.send_error(404)
                return
            page = int(parse_qs(parsed.query).get("page", ["1"])[0])
            values = documents if parsed.path.endswith("documents") else files
            start = (page - 1) * 100
            payload_key = "documents" if parsed.path.endswith("documents") else "files"
            payload = {payload_key: values[start : start + 100]}
            self._send_json(payload)

        def _send_json(self, payload):
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", len(documents), len(files)
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
