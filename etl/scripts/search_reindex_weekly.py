#!/usr/bin/env python3
# search_reindex_weekly.py - Weekly full reindex of MeiliSearch
# Originally Python 2.7, minimally ported to Python 3 in 2021
# Clears MeiliSearch indices, paginates through document-service and
# file-service APIs, bulk-indexes into MeiliSearch, validates counts
#
# Owner: Jake (data-team@otterworks.dev) -- Jake left mid-2020
# TODO ETL-112: Add retry logic for transient API failures (2019-12-20)
# TODO ETL-145: Use connection pooling for requests (deferred Q3 2020)
# TODO ETL-188: Add timeout handling everywhere (never done)

import configparser
import json
import sys
import time
from datetime import datetime

import requests

DOCUMENTS_INDEX = "documents"
FILES_INDEX = "files"
API_PAGE_SIZE = 100
TASK_TIMEOUT_SECONDS = 60
INDEX_TASK_TIMEOUT_SECONDS = 120

DOCS_SETTINGS = {
    "searchableAttributes": ["title", "content", "tags"],
    "filterableAttributes": ["type", "owner_id", "tags", "created_at", "updated_at"],
    "sortableAttributes": ["updated_at", "created_at"],
    "rankingRules": ["words", "typo", "proximity", "attribute", "sort", "exactness"],
}

FILES_SETTINGS = {
    "searchableAttributes": ["name", "tags", "mime_type"],
    "filterableAttributes": ["type", "owner_id", "mime_type", "folder_id", "tags", "created_at", "updated_at"],
    "sortableAttributes": ["updated_at", "created_at", "size"],
    "rankingRules": ["words", "typo", "proximity", "attribute", "sort", "exactness"],
}


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Meili(object):
    """Minimal MeiliSearch endpoint holder (URL + auth headers)."""

    def __init__(self, url, api_key):
        self.url = url
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = "Bearer %s" % api_key


def wait_for_task(meili, task_uid, timeout):
    """Poll a task until it succeeds/fails; returns its final payload, or None on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task_resp = requests.get(
            "%s/tasks/%s" % (meili.url, task_uid),
            headers=meili.headers,
        )
        task_resp.raise_for_status()
        payload = task_resp.json()
        if payload.get("status") in ("succeeded", "failed"):
            return payload
        time.sleep(1)
    return None


def task_failed(task):
    return task is not None and task.get("status") == "failed"


def delete_index(meili, index_name):
    try:
        resp = requests.delete(
            "%s/indexes/%s" % (meili.url, index_name),
            headers=meili.headers,
        )
        if resp.ok:
            task_uid = resp.json().get("taskUid")
            if task_uid is not None:
                task = wait_for_task(meili, task_uid, TASK_TIMEOUT_SECONDS)
                if task_failed(task):
                    print("[%s] WARNING: Delete task %s failed" % (now_str(), task_uid))
            print("[%s] Deleted index: %s" % (now_str(), index_name))
    except:
        print("[%s] Index %s did not exist, skipping delete" % (now_str(), index_name))


def create_index(meili, index_name):
    resp = requests.post(
        "%s/indexes" % meili.url,
        headers=meili.headers,
        data=json.dumps({"uid": index_name, "primaryKey": "id"}),
    )
    resp.raise_for_status()
    task_uid = resp.json().get("taskUid")
    if task_uid is not None:
        wait_for_task(meili, task_uid, TASK_TIMEOUT_SECONDS)
    print("[%s] Created index: %s" % (now_str(), index_name))


def configure_index(meili, index_name, settings):
    resp = requests.patch(
        "%s/indexes/%s/settings" % (meili.url, index_name),
        headers=meili.headers,
        data=json.dumps(settings),
    )
    resp.raise_for_status()
    task_uid = resp.json().get("taskUid")
    if task_uid is not None:
        wait_for_task(meili, task_uid, TASK_TIMEOUT_SECONDS)


def submit_batch(meili, index_name, batch):
    index_resp = requests.post(
        "%s/indexes/%s/documents" % (meili.url, index_name),
        headers=meili.headers,
        data=json.dumps(batch),
    )
    index_resp.raise_for_status()
    task_uid = index_resp.json().get("taskUid")
    if task_uid is None:
        return
    task = wait_for_task(meili, task_uid, INDEX_TASK_TIMEOUT_SECONDS)
    if task_failed(task):
        print("[%s] WARNING: Index task failed: %s" % (now_str(), task.get("error", {})))


def index_entities(meili, index_name, fetch_page, to_document):
    indexed = 0
    page = 1

    while True:
        items = fetch_page(page)
        if not items:
            break

        submit_batch(meili, index_name, [to_document(item) for item in items])
        indexed += len(items)

        if len(items) < API_PAGE_SIZE:
            break
        page += 1

    return indexed


def fetch_documents_page(document_service_url, page):
    # No session reuse, no timeout, no retry -- just raw requests
    resp = requests.get(
        "%s/api/v1/documents" % document_service_url,
        params={"page": page, "size": API_PAGE_SIZE},
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("documents", data.get("items", []))


def fetch_files_page(file_service_url, page):
    resp = requests.get(
        "%s/api/v1/files" % file_service_url,
        params={"page": page, "page_size": API_PAGE_SIZE},
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("files", data.get("items", []))


def document_to_index_entry(doc):
    return {
        "id": doc.get("document_id", doc.get("id", "")),
        "title": doc.get("title", ""),
        "content": doc.get("content", ""),
        "owner_id": doc.get("owner_id", ""),
        "tags": doc.get("tags", []),
        "type": "document",
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


def file_to_index_entry(f):
    return {
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
    }


def index_document_count(meili, index_name):
    stats = requests.get(
        "%s/indexes/%s/stats" % (meili.url, index_name),
        headers=meili.headers,
    )
    stats.raise_for_status()
    return stats.json().get("numberOfDocuments", 0)


def main():
    print("[%s] search_reindex_weekly.py starting..." % now_str())

    # ---- Load config ----
    config = configparser.ConfigParser()
    config.read("/opt/etl/config.ini")

    document_service_url = config.get("services", "document_service_url")
    file_service_url = config.get("services", "file_service_url")

    meili = Meili(
        config.get("services", "meilisearch_url"),
        config.get("services", "meilisearch_api_key"),
    )

    # ---- Clear existing indices ----
    print("[%s] Clearing MeiliSearch indices..." % now_str())

    for index_name in [DOCUMENTS_INDEX, FILES_INDEX]:
        delete_index(meili, index_name)

    # ---- Create indices ----
    for index_name in [DOCUMENTS_INDEX, FILES_INDEX]:
        create_index(meili, index_name)

    # ---- Configure index settings ----
    configure_index(meili, DOCUMENTS_INDEX, DOCS_SETTINGS)
    configure_index(meili, FILES_INDEX, FILES_SETTINGS)

    print("[%s] MeiliSearch indices configured" % now_str())

    # ---- Fetch and index documents ----
    print("[%s] Indexing documents from document-service..." % now_str())

    docs_indexed = index_entities(
        meili,
        DOCUMENTS_INDEX,
        lambda page: fetch_documents_page(document_service_url, page),
        document_to_index_entry,
    )

    print("[%s] Indexed %d documents into %s" % (now_str(), docs_indexed, DOCUMENTS_INDEX))

    # ---- Fetch and index files ----
    print("[%s] Indexing files from file-service..." % now_str())

    files_indexed = index_entities(
        meili,
        FILES_INDEX,
        lambda page: fetch_files_page(file_service_url, page),
        file_to_index_entry,
    )

    print("[%s] Indexed %d files into %s" % (now_str(), files_indexed, FILES_INDEX))

    # ---- Validate index counts ----
    print("[%s] Validating index counts..." % now_str())

    docs_count = index_document_count(meili, DOCUMENTS_INDEX)
    files_count = index_document_count(meili, FILES_INDEX)

    print("[%s] Validation: documents=%d (expected %d), files=%d (expected %d)" % (
        now_str(),
        docs_count, docs_indexed,
        files_count, files_indexed,
    ))

    if docs_count != docs_indexed:
        print("[%s] ERROR: Documents index count mismatch: %d != %d" % (
            now_str(), docs_count, docs_indexed
        ))
        sys.exit(1)
    if files_count != files_indexed:
        print("[%s] ERROR: Files index count mismatch: %d != %d" % (
            now_str(), files_count, files_indexed
        ))
        sys.exit(1)

    print("[%s] search_reindex_weekly.py completed successfully" % now_str())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("[%s] FATAL: %s" % (now_str(), str(e)))
        sys.exit(1)
