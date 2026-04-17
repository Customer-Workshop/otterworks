"""
OtterWorks Search Reindex Pipeline

Weekly full reindex of all documents and files into OpenSearch.
Queries document-service and file-service APIs, bulk-indexes into
OpenSearch, validates counts, and optionally swaps aliases for
blue/green indexing.
"""

import json
import logging
from datetime import datetime, timedelta

import requests
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.amazon.aws.hooks.base_aws import AwsBaseHook

logger = logging.getLogger(__name__)

# Configuration
DOCUMENT_SERVICE_URL = "{{ var.value.get('document_service_url', 'http://document-service:8083') }}"
FILE_SERVICE_URL = "{{ var.value.get('file_service_url', 'http://file-service:8082') }}"
OPENSEARCH_URL = "{{ var.value.get('opensearch_url', 'https://opensearch.otterworks.internal:9200') }}"
INDEX_PREFIX = "otterworks"
DOCUMENTS_INDEX = f"{INDEX_PREFIX}-documents"
FILES_INDEX = f"{INDEX_PREFIX}-files"
ALIAS_DOCUMENTS = f"{INDEX_PREFIX}-documents-live"
ALIAS_FILES = f"{INDEX_PREFIX}-files-live"
BULK_BATCH_SIZE = 500
API_PAGE_SIZE = 100
REQUEST_TIMEOUT = 30

default_args = {
    "owner": "otterworks-search",
    "depends_on_past": False,
    "email_on_failure": True,
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
}


def _opensearch_session():
    """Create a requests session for OpenSearch with appropriate headers."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


def _get_timestamped_index(base_name):
    """Generate a timestamped index name for blue/green deployment."""
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"{base_name}-{ts}"


def create_indices(**context):
    """Create fresh OpenSearch indices with appropriate mappings.

    Uses timestamped index names for blue/green indexing strategy.
    """
    docs_index = _get_timestamped_index(DOCUMENTS_INDEX)
    files_index = _get_timestamped_index(FILES_INDEX)

    session = _opensearch_session()

    documents_mapping = {
        "settings": {
            "number_of_shards": 2,
            "number_of_replicas": 1,
            "analysis": {
                "analyzer": {
                    "content_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "stop", "snowball"],
                    }
                }
            },
        },
        "mappings": {
            "properties": {
                "document_id": {"type": "keyword"},
                "title": {"type": "text", "analyzer": "content_analyzer", "fields": {"keyword": {"type": "keyword"}}},
                "content": {"type": "text", "analyzer": "content_analyzer"},
                "owner_id": {"type": "keyword"},
                "folder_id": {"type": "keyword"},
                "content_type": {"type": "keyword"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
                "version": {"type": "integer"},
                "word_count": {"type": "integer"},
                "tags": {"type": "keyword"},
            }
        },
    }

    files_mapping = {
        "settings": {
            "number_of_shards": 2,
            "number_of_replicas": 1,
        },
        "mappings": {
            "properties": {
                "file_id": {"type": "keyword"},
                "file_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "owner_id": {"type": "keyword"},
                "folder_id": {"type": "keyword"},
                "mime_type": {"type": "keyword"},
                "size_bytes": {"type": "long"},
                "s3_key": {"type": "keyword"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
                "tags": {"type": "keyword"},
            }
        },
    }

    resp = session.put(
        f"{OPENSEARCH_URL}/{docs_index}",
        data=json.dumps(documents_mapping),
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    logger.info("Created documents index: %s", docs_index)

    resp = session.put(
        f"{OPENSEARCH_URL}/{files_index}",
        data=json.dumps(files_mapping),
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    logger.info("Created files index: %s", files_index)

    context["ti"].xcom_push(key="docs_index", value=docs_index)
    context["ti"].xcom_push(key="files_index", value=files_index)


def fetch_and_index_documents(**context):
    """Query all documents from document-service API and bulk index into OpenSearch.

    Paginates through the document-service REST API and sends bulk
    index requests to OpenSearch in batches of BULK_BATCH_SIZE.
    """
    docs_index = context["ti"].xcom_pull(key="docs_index", task_ids="create_indices")
    session = _opensearch_session()

    total_indexed = 0
    page = 0

    while True:
        resp = requests.get(
            f"{DOCUMENT_SERVICE_URL}/api/v1/documents",
            params={"page": page, "page_size": API_PAGE_SIZE},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        documents = data.get("documents", data.get("items", []))

        if not documents:
            break

        bulk_body = _build_bulk_body(documents, docs_index, id_field="document_id")
        _send_bulk_request(session, bulk_body)
        total_indexed += len(documents)

        if len(documents) < API_PAGE_SIZE:
            break
        page += 1

    logger.info("Indexed %d documents into %s", total_indexed, docs_index)
    context["ti"].xcom_push(key="docs_indexed", value=total_indexed)


def fetch_and_index_files(**context):
    """Query all files from file-service API and bulk index into OpenSearch.

    Paginates through the file-service REST API and sends bulk
    index requests to OpenSearch in batches of BULK_BATCH_SIZE.
    """
    files_index = context["ti"].xcom_pull(key="files_index", task_ids="create_indices")
    session = _opensearch_session()

    total_indexed = 0
    page = 0

    while True:
        resp = requests.get(
            f"{FILE_SERVICE_URL}/api/v1/files",
            params={"page": page, "page_size": API_PAGE_SIZE},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        files = data.get("files", data.get("items", []))

        if not files:
            break

        bulk_body = _build_bulk_body(files, files_index, id_field="file_id")
        _send_bulk_request(session, bulk_body)
        total_indexed += len(files)

        if len(files) < API_PAGE_SIZE:
            break
        page += 1

    logger.info("Indexed %d files into %s", total_indexed, files_index)
    context["ti"].xcom_push(key="files_indexed", value=total_indexed)


def _build_bulk_body(items, index_name, id_field):
    """Build an OpenSearch bulk request body from a list of items."""
    lines = []
    for item in items:
        doc_id = item.get(id_field, item.get("id", ""))
        action = {"index": {"_index": index_name, "_id": doc_id}}
        lines.append(json.dumps(action))
        lines.append(json.dumps(item))
    return "\n".join(lines) + "\n"


def _send_bulk_request(session, bulk_body):
    """Send a bulk index request to OpenSearch with error checking."""
    resp = session.post(
        f"{OPENSEARCH_URL}/_bulk",
        data=bulk_body,
        timeout=REQUEST_TIMEOUT * 2,
    )
    resp.raise_for_status()
    result = resp.json()
    if result.get("errors"):
        error_count = sum(
            1
            for item in result.get("items", [])
            if "error" in item.get("index", {})
        )
        logger.warning("Bulk index had %d errors", error_count)


def validate_indices(**context):
    """Validate that the new indices have the expected document counts.

    Compares the count of indexed documents/files with what was reported
    during the indexing phase. Fails if counts don't match.
    """
    docs_index = context["ti"].xcom_pull(key="docs_index", task_ids="create_indices")
    files_index = context["ti"].xcom_pull(key="files_index", task_ids="create_indices")
    docs_indexed = context["ti"].xcom_pull(key="docs_indexed", task_ids="fetch_and_index_documents") or 0
    files_indexed = context["ti"].xcom_pull(key="files_indexed", task_ids="fetch_and_index_files") or 0

    session = _opensearch_session()

    # Refresh indices to make all docs searchable
    session.post(f"{OPENSEARCH_URL}/{docs_index}/_refresh", timeout=REQUEST_TIMEOUT)
    session.post(f"{OPENSEARCH_URL}/{files_index}/_refresh", timeout=REQUEST_TIMEOUT)

    docs_count = _get_index_count(session, docs_index)
    files_count = _get_index_count(session, files_index)

    logger.info(
        "Validation: documents=%d (expected %d), files=%d (expected %d)",
        docs_count,
        docs_indexed,
        files_count,
        files_indexed,
    )

    if docs_count != docs_indexed:
        raise ValueError(
            f"Documents index count mismatch: {docs_count} != {docs_indexed}"
        )
    if files_count != files_indexed:
        raise ValueError(
            f"Files index count mismatch: {files_count} != {files_indexed}"
        )

    context["ti"].xcom_push(key="validation_passed", value=True)


def _get_index_count(session, index_name):
    """Get the document count for an OpenSearch index."""
    resp = session.get(
        f"{OPENSEARCH_URL}/{index_name}/_count",
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("count", 0)


def swap_aliases(**context):
    """Swap OpenSearch aliases to point to new indices (blue/green).

    Atomically removes old index from alias and adds new index,
    then deletes the old index to free resources.
    """
    docs_index = context["ti"].xcom_pull(key="docs_index", task_ids="create_indices")
    files_index = context["ti"].xcom_pull(key="files_index", task_ids="create_indices")
    validation_passed = context["ti"].xcom_pull(
        key="validation_passed", task_ids="validate_indices"
    )

    if not validation_passed:
        logger.error("Skipping alias swap — validation did not pass")
        return

    session = _opensearch_session()

    _swap_alias(session, ALIAS_DOCUMENTS, docs_index)
    _swap_alias(session, ALIAS_FILES, files_index)

    logger.info(
        "Aliases swapped: %s -> %s, %s -> %s",
        ALIAS_DOCUMENTS,
        docs_index,
        ALIAS_FILES,
        files_index,
    )


def _swap_alias(session, alias_name, new_index):
    """Atomically swap an alias from old index to new index."""
    # Find current indices attached to alias
    current_resp = session.get(
        f"{OPENSEARCH_URL}/_alias/{alias_name}",
        timeout=REQUEST_TIMEOUT,
    )

    actions = []
    if current_resp.status_code == 200:
        current_indices = list(current_resp.json().keys())
        for old_index in current_indices:
            actions.append({"remove": {"index": old_index, "alias": alias_name}})
    actions.append({"add": {"index": new_index, "alias": alias_name}})

    resp = session.post(
        f"{OPENSEARCH_URL}/_aliases",
        data=json.dumps({"actions": actions}),
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()

    # Clean up old indices
    if current_resp.status_code == 200:
        for old_index in current_indices:
            if old_index != new_index:
                delete_resp = session.delete(
                    f"{OPENSEARCH_URL}/{old_index}",
                    timeout=REQUEST_TIMEOUT,
                )
                if delete_resp.ok:
                    logger.info("Deleted old index: %s", old_index)


with DAG(
    "otterworks_search_reindex",
    default_args=default_args,
    description="Weekly full reindex of documents and files into OpenSearch",
    schedule="@weekly",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["otterworks", "search", "opensearch", "etl"],
    doc_md=__doc__,
    max_active_runs=1,
) as dag:

    create = PythonOperator(
        task_id="create_indices",
        python_callable=create_indices,
    )

    index_docs = PythonOperator(
        task_id="fetch_and_index_documents",
        python_callable=fetch_and_index_documents,
    )

    index_files = PythonOperator(
        task_id="fetch_and_index_files",
        python_callable=fetch_and_index_files,
    )

    validate = PythonOperator(
        task_id="validate_indices",
        python_callable=validate_indices,
    )

    swap = PythonOperator(
        task_id="swap_aliases",
        python_callable=swap_aliases,
    )

    # Create indices, then index docs/files in parallel, validate, swap aliases
    create >> [index_docs, index_files] >> validate >> swap
