import requests


def test_search_reindex_paginates_and_indexes(
    etl_config, load_script, meilisearch_service, http_stub
):
    service_url, document_count, file_count = http_stub
    etl_config(
        document_service_url=service_url,
        file_service_url=service_url,
        meilisearch_url=meilisearch_service["url"],
        meilisearch_api_key=meilisearch_service["api_key"],
    )

    load_script("search_reindex_weekly.py").main()

    headers = {"Authorization": f"Bearer {meilisearch_service['api_key']}"}
    assert requests.get(
        f"{meilisearch_service['url']}/indexes/documents/stats", headers=headers
    ).json()["numberOfDocuments"] == document_count
    assert requests.get(
        f"{meilisearch_service['url']}/indexes/files/stats", headers=headers
    ).json()["numberOfDocuments"] == file_count
