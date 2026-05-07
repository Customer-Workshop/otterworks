"""
OtterWorks Search Reindex Pipeline

Weekly full reindex of all documents and files into MeiliSearch.
Queries document-service and file-service APIs, bulk-indexes into
MeiliSearch, and validates counts.
"""

import json
import logging
from datetime import datetime, timedelta

import requests
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.amazon.aws.hooks.base_aws import AwsBaseHook

logger = logging.getLogger(__name__)

# Configuration defaults
_DEFAULT_DOCUMENT_SERVICE_URL = "http://document-service:8083"
_DEFAULT_FILE_SERVICE_URL = "http://file-service:8082"
_DEFAULT_MEILISEARCH_URL = "http://meilisearch:7700"
DOCUMENTS_INDEX = "documents"
FILES_INDEX = "files"
BULK_BATCH_SIZE = 500
API_PAGE_SIZE = 100
REQUEST_TIMEOUT = 30


def _get_document_service_url():
    from airflow.models import Variable
    return Variable.get("document_service_url", default_var=_DEFAULT_DOCUMENT_SERVICE_URL)


def _get_file_service_url():
    from airflow.models import Variable
    return Variable.get("file_service_url", default_var=_DEFAULT_FILE_SERVICE_URL)


def _get_meilisearch_url():
    from airflow.models import Variable
    return Variable.get("meilisearch_url", default_var=_DEFAULT_MEILISEARCH_URL)


def _get_meilisearch_api_key():
    from airflow.models import Variable
    return Variable.get("meilisearch_api_key", default_var="")


def _meilisearch_session():
    """Create a requests session for MeiliSearch with appropriate headers."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    api_key = _get_meilisearch_api_key()
    if api_key:
        session.headers.update({"Authorization": f"Bearer {api_key}"})
    return session


def _wait_for_task(session, meilisearch_url, task_uid, timeout=60):
    """Poll MeiliSearch until a task completes or times out."""
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = session.get(
            f"{meilisearch_url}/tasks/{task_uid}",
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        status = resp.json().get("status")
        if status == "succeeded":
            return
        if status == "failed":
            error = resp.json().get("error", {})
            raise RuntimeError(f"MeiliSearch task {task_uid} failed: {error}")
        time.sleep(1)
    raise TimeoutError(f"MeiliSearch task {task_uid} timed out after {timeout}s")


default_args = {
    "owner": "otterworks-search",
    "depends_on_past": False,
    "email_on_failure": True,
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
}


def clear_indices(**context):
    """Delete and recreate MeiliSearch indices with appropriate settings."""
    session = _meilisearch_session()
    meilisearch_url = _get_meilisearch_url()

    for index_name in [DOCUMENTS_INDEX, FILES_INDEX]:
        try:
            resp = session.delete(
                f"{meilisearch_url}/indexes/{index_name}",
                timeout=REQUEST_TIMEOUT,
            )
            if resp.ok:
                task_uid = resp.json().get("taskUid")
                if task_uid is not None:
                    _wait_for_task(session, meilisearch_url, task_uid)
                logger.info("Deleted index: %s", index_name)
        except Exception:
            logger.info("Index %s did not exist, skipping delete", index_name)

    for index_name in [DOCUMENTS_INDEX, FILES_INDEX]:
        resp = session.post(
            f"{meilisearch_url}/indexes",
            data=json.dumps({"uid": index_name, "primaryKey": "id"}),
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        task_uid = resp.json().get("taskUid")
        if task_uid is not None:
            _wait_for_task(session, meilisearch_url, task_uid)
        logger.info("Created index: %s", index_name)

    # Configure documents index
    docs_settings = {
        "searchableAttributes": ["title", "content", "tags"],
        "filterableAttributes": ["type", "owner_id", "tags", "created_at", "updated_at"],
        "sortableAttributes": ["updated_at", "created_at"],
        "rankingRules": ["words", "typo", "proximity", "attribute", "sort", "exactness"],
    }
    resp = session.patch(
        f"{meilisearch_url}/indexes/{DOCUMENTS_INDEX}/settings",
        data=json.dumps(docs_settings),
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    task_uid = resp.json().get("taskUid")
    if task_uid is not None:
        _wait_for_task(session, meilisearch_url, task_uid)

    # Configure files index
    files_settings = {
        "searchableAttributes": ["name", "tags", "mime_type"],
        "filterableAttributes": ["type", "owner_id", "mime_type", "folder_id", "tags", "created_at", "updated_at"],
        "sortableAttributes": ["updated_at", "created_at", "size"],
        "rankingRules": ["words", "typo", "proximity", "attribute", "sort", "exactness"],
    }
    resp = session.patch(
        f"{meilisearch_url}/indexes/{FILES_INDEX}/settings",
        data=json.dumps(files_settings),
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    task_uid = resp.json().get("taskUid")
    if task_uid is not None:
        _wait_for_task(session, meilisearch_url, task_uid)

    logger.info("MeiliSearch indices configured")


def fetch_and_index_documents(**context):
    """Query all documents from document-service API and index into MeiliSearch.

    Paginates through the document-service REST API and sends batch
    add_documents requests to MeiliSearch.
    """
    session = _meilisearch_session()
    meilisearch_url = _get_meilisearch_url()

    total_indexed = 0
    page = 0

    while True:
        resp = requests.get(
            f"{_get_document_service_url()}/api/v1/documents",
            params={"page": page, "page_size": API_PAGE_SIZE},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        documents = data.get("documents", data.get("items", []))

        if not documents:
            break

        # Normalize documents for MeiliSearch
        batch = []
        for doc in documents:
            batch.append({
                "id": doc.get("document_id", doc.get("id", "")),
                "title": doc.get("title", ""),
                "content": doc.get("content", ""),
                "owner_id": doc.get("owner_id", ""),
                "tags": doc.get("tags", []),
                "type": "document",
                "created_at": doc.get("created_at"),
                "updated_at": doc.get("updated_at"),
            })

        index_resp = session.post(
            f"{meilisearch_url}/indexes/{DOCUMENTS_INDEX}/documents",
            data=json.dumps(batch),
            timeout=REQUEST_TIMEOUT * 2,
        )
        index_resp.raise_for_status()
        task_uid = index_resp.json().get("taskUid")
        if task_uid is not None:
            _wait_for_task(session, meilisearch_url, task_uid, timeout=120)
        total_indexed += len(documents)

        if len(documents) < API_PAGE_SIZE:
            break
        page += 1

    logger.info("Indexed %d documents into %s", total_indexed, DOCUMENTS_INDEX)
    context["ti"].xcom_push(key="docs_indexed", value=total_indexed)


def fetch_and_index_files(**context):
    """Query all files from file-service API and index into MeiliSearch.

    Paginates through the file-service REST API and sends batch
    add_documents requests to MeiliSearch.
    """
    session = _meilisearch_session()
    meilisearch_url = _get_meilisearch_url()

    total_indexed = 0
    page = 0

    while True:
        resp = requests.get(
            f"{_get_file_service_url()}/api/v1/files",
            params={"page": page, "page_size": API_PAGE_SIZE},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        files = data.get("files", data.get("items", []))

        if not files:
            break

        # Normalize files for MeiliSearch
        batch = []
        for f in files:
            batch.append({
                "id": f.get("file_id", f.get("id", "")),
                "name": f.get("file_name", f.get("name", "")),
                "owner_id": f.get("owner_id", ""),
                "mime_type": f.get("mime_type", ""),
                "folder_id": f.get("folder_id", ""),
                "size": f.get("size_bytes", f.get("size", 0)),
                "tags": f.get("tags", []),
                "type": "file",
                "created_at": f.get("created_at"),
                "updated_at": f.get("updated_at"),
            })

        index_resp = session.post(
            f"{meilisearch_url}/indexes/{FILES_INDEX}/documents",
            data=json.dumps(batch),
            timeout=REQUEST_TIMEOUT * 2,
        )
        index_resp.raise_for_status()
        task_uid = index_resp.json().get("taskUid")
        if task_uid is not None:
            _wait_for_task(session, meilisearch_url, task_uid, timeout=120)
        total_indexed += len(files)

        if len(files) < API_PAGE_SIZE:
            break
        page += 1

    logger.info("Indexed %d files into %s", total_indexed, FILES_INDEX)
    context["ti"].xcom_push(key="files_indexed", value=total_indexed)


def validate_indices(**context):
    """Validate that the indices have the expected document counts.

    Compares the count of indexed documents/files with what was reported
    during the indexing phase. Fails if counts don't match.
    """
    docs_indexed = context["ti"].xcom_pull(key="docs_indexed", task_ids="fetch_and_index_documents") or 0
    files_indexed = context["ti"].xcom_pull(key="files_indexed", task_ids="fetch_and_index_files") or 0

    session = _meilisearch_session()
    meilisearch_url = _get_meilisearch_url()

    docs_stats = session.get(
        f"{meilisearch_url}/indexes/{DOCUMENTS_INDEX}/stats",
        timeout=REQUEST_TIMEOUT,
    )
    docs_stats.raise_for_status()
    docs_count = docs_stats.json().get("numberOfDocuments", 0)

    files_stats = session.get(
        f"{meilisearch_url}/indexes/{FILES_INDEX}/stats",
        timeout=REQUEST_TIMEOUT,
    )
    files_stats.raise_for_status()
    files_count = files_stats.json().get("numberOfDocuments", 0)

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


with DAG(
    "otterworks_search_reindex",
    default_args=default_args,
    description="Weekly full reindex of documents and files into MeiliSearch",
    schedule="@weekly",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["otterworks", "search", "meilisearch", "etl"],
    doc_md=__doc__,
    max_active_runs=1,
) as dag:

    clear = PythonOperator(
        task_id="clear_indices",
        python_callable=clear_indices,
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

    # Clear indices, then index docs/files in parallel, then validate
    clear >> [index_docs, index_files] >> validate
