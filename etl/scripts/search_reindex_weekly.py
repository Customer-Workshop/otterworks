#!/usr/bin/env python3
# search_reindex_weekly.py - Weekly full reindex of MeiliSearch
# Originally Python 2.7, minimally ported to Python 3 in 2021
# Clears MeiliSearch indices, paginates through document-service and
# file-service APIs, bulk-indexes into MeiliSearch, validates counts

import configparser
import json
import sys
import time
from datetime import datetime

import requests

_TIMESTAMP_FMT = "%Y-%m-%d %H:%M:%S"


def _wait_for_task(meilisearch_url, meili_headers, task_uid, timeout=60):
    """Poll MeiliSearch until a task reaches a terminal state."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task_resp = requests.get(
            "%s/tasks/%s" % (meilisearch_url, task_uid),
            headers=meili_headers,
        )
        task_resp.raise_for_status()
        status = task_resp.json().get("status")
        if status in ("succeeded", "failed"):
            return task_resp.json()
        time.sleep(1)
    return None


def main():
    print("[%s] search_reindex_weekly.py starting..." % datetime.now().strftime(_TIMESTAMP_FMT))

    # ---- Load config ----
    config = configparser.ConfigParser()
    config.read("/opt/etl/config.ini")

    document_service_url = config.get("services", "document_service_url")
    file_service_url = config.get("services", "file_service_url")
    meilisearch_url = config.get("services", "meilisearch_url")
    meilisearch_api_key = config.get("services", "meilisearch_api_key")

    documents_index = "documents"
    files_index = "files"
    api_page_size = 100

    meili_headers = {"Content-Type": "application/json"}
    if meilisearch_api_key:
        meili_headers["Authorization"] = "Bearer %s" % meilisearch_api_key

    # ---- Clear existing indices ----
    print("[%s] Clearing MeiliSearch indices..." % datetime.now().strftime(_TIMESTAMP_FMT))

    for index_name in [documents_index, files_index]:
        try:
            resp = requests.delete(
                "%s/indexes/%s" % (meilisearch_url, index_name),
                headers=meili_headers,
            )
            if resp.ok:
                task_uid = resp.json().get("taskUid")
                if task_uid is not None:
                    result = _wait_for_task(meilisearch_url, meili_headers, task_uid)
                    if result and result.get("status") == "failed":
                        print("[%s] WARNING: Delete task %s failed" % (datetime.now().strftime(_TIMESTAMP_FMT), task_uid))
                print("[%s] Deleted index: %s" % (datetime.now().strftime(_TIMESTAMP_FMT), index_name))
        except Exception:
            print("[%s] Index %s did not exist, skipping delete" % (datetime.now().strftime(_TIMESTAMP_FMT), index_name))

    # ---- Create indices ----
    for index_name in [documents_index, files_index]:
        resp = requests.post(
            "%s/indexes" % meilisearch_url,
            headers=meili_headers,
            data=json.dumps({"uid": index_name, "primaryKey": "id"}),
        )
        resp.raise_for_status()
        task_uid = resp.json().get("taskUid")
        if task_uid is not None:
            _wait_for_task(meilisearch_url, meili_headers, task_uid)
        print("[%s] Created index: %s" % (datetime.now().strftime(_TIMESTAMP_FMT), index_name))

    # ---- Configure documents index settings ----
    docs_settings = {
        "searchableAttributes": ["title", "content", "tags"],
        "filterableAttributes": ["type", "owner_id", "tags", "created_at", "updated_at"],
        "sortableAttributes": ["updated_at", "created_at"],
        "rankingRules": ["words", "typo", "proximity", "attribute", "sort", "exactness"],
    }
    resp = requests.patch(
        "%s/indexes/%s/settings" % (meilisearch_url, documents_index),
        headers=meili_headers,
        data=json.dumps(docs_settings),
    )
    resp.raise_for_status()
    task_uid = resp.json().get("taskUid")
    if task_uid is not None:
        _wait_for_task(meilisearch_url, meili_headers, task_uid)

    # ---- Configure files index settings ----
    files_settings = {
        "searchableAttributes": ["name", "tags", "mime_type"],
        "filterableAttributes": ["type", "owner_id", "mime_type", "folder_id", "tags", "created_at", "updated_at"],
        "sortableAttributes": ["updated_at", "created_at", "size"],
        "rankingRules": ["words", "typo", "proximity", "attribute", "sort", "exactness"],
    }
    resp = requests.patch(
        "%s/indexes/%s/settings" % (meilisearch_url, files_index),
        headers=meili_headers,
        data=json.dumps(files_settings),
    )
    resp.raise_for_status()
    task_uid = resp.json().get("taskUid")
    if task_uid is not None:
        _wait_for_task(meilisearch_url, meili_headers, task_uid)

    print("[%s] MeiliSearch indices configured" % datetime.now().strftime(_TIMESTAMP_FMT))

    # ---- Fetch and index documents ----
    print("[%s] Indexing documents from document-service..." % datetime.now().strftime(_TIMESTAMP_FMT))

    docs_indexed = 0
    page = 1

    while True:
        resp = requests.get(
            "%s/api/v1/documents" % document_service_url,
            params={"page": page, "size": api_page_size},
        )
        resp.raise_for_status()
        data = resp.json()
        documents = data.get("documents", data.get("items", []))

        if not documents:
            break

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

        index_resp = requests.post(
            "%s/indexes/%s/documents" % (meilisearch_url, documents_index),
            headers=meili_headers,
            data=json.dumps(batch),
        )
        index_resp.raise_for_status()
        task_uid = index_resp.json().get("taskUid")
        if task_uid is not None:
            result = _wait_for_task(meilisearch_url, meili_headers, task_uid, timeout=120)
            if result and result.get("status") == "failed":
                error = result.get("error", {})
                print("[%s] WARNING: Index task failed: %s" % (datetime.now().strftime(_TIMESTAMP_FMT), error))
        docs_indexed += len(documents)

        if len(documents) < api_page_size:
            break
        page += 1

    print("[%s] Indexed %d documents into %s" % (datetime.now().strftime(_TIMESTAMP_FMT), docs_indexed, documents_index))

    # ---- Fetch and index files ----
    print("[%s] Indexing files from file-service..." % datetime.now().strftime(_TIMESTAMP_FMT))

    files_indexed = 0
    page = 1

    while True:
        resp = requests.get(
            "%s/api/v1/files" % file_service_url,
            params={"page": page, "page_size": api_page_size},
        )
        resp.raise_for_status()
        data = resp.json()
        files = data.get("files", data.get("items", []))

        if not files:
            break

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

        index_resp = requests.post(
            "%s/indexes/%s/documents" % (meilisearch_url, files_index),
            headers=meili_headers,
            data=json.dumps(batch),
        )
        index_resp.raise_for_status()
        task_uid = index_resp.json().get("taskUid")
        if task_uid is not None:
            result = _wait_for_task(meilisearch_url, meili_headers, task_uid, timeout=120)
            if result and result.get("status") == "failed":
                error = result.get("error", {})
                print("[%s] WARNING: Index task failed: %s" % (datetime.now().strftime(_TIMESTAMP_FMT), error))
        files_indexed += len(files)

        if len(files) < api_page_size:
            break
        page += 1

    print("[%s] Indexed %d files into %s" % (datetime.now().strftime(_TIMESTAMP_FMT), files_indexed, files_index))

    # ---- Validate index counts ----
    print("[%s] Validating index counts..." % datetime.now().strftime(_TIMESTAMP_FMT))

    docs_stats = requests.get(
        "%s/indexes/%s/stats" % (meilisearch_url, documents_index),
        headers=meili_headers,
    )
    docs_stats.raise_for_status()
    docs_count = docs_stats.json().get("numberOfDocuments", 0)

    files_stats = requests.get(
        "%s/indexes/%s/stats" % (meilisearch_url, files_index),
        headers=meili_headers,
    )
    files_stats.raise_for_status()
    files_count = files_stats.json().get("numberOfDocuments", 0)

    print("[%s] Validation: documents=%d (expected %d), files=%d (expected %d)" % (
        datetime.now().strftime(_TIMESTAMP_FMT),
        docs_count, docs_indexed,
        files_count, files_indexed,
    ))

    if docs_count != docs_indexed:
        print("[%s] ERROR: Documents index count mismatch: %d != %d" % (
            datetime.now().strftime(_TIMESTAMP_FMT), docs_count, docs_indexed
        ))
        sys.exit(1)
    if files_count != files_indexed:
        print("[%s] ERROR: Files index count mismatch: %d != %d" % (
            datetime.now().strftime(_TIMESTAMP_FMT), files_count, files_indexed
        ))
        sys.exit(1)

    print("[%s] search_reindex_weekly.py completed successfully" % datetime.now().strftime(_TIMESTAMP_FMT))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("[%s] FATAL: %s" % (datetime.now().strftime(_TIMESTAMP_FMT), str(e)))
        sys.exit(1)
