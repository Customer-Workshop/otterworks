use serde::Serialize;

/// Fire-and-forget client for synchronously indexing files in the search service.
/// Falls back silently on failure — the async SNS/SQS pipeline serves as backup.
#[derive(Clone)]
pub struct SearchIndexClient {
    http: reqwest::Client,
    base_url: String,
}

#[derive(Serialize)]
struct IndexFilePayload {
    id: String,
    name: String,
    mime_type: String,
    owner_id: String,
    folder_id: String,
    size: u64,
    created_at: String,
}

impl SearchIndexClient {
    pub fn new(search_service_url: &str) -> Self {
        Self {
            http: reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(3))
                .build()
                .unwrap_or_default(),
            base_url: search_service_url.trim_end_matches('/').to_string(),
        }
    }

    /// Index a file synchronously. Errors are logged but never propagated.
    pub async fn index_file(
        &self,
        id: &str,
        name: &str,
        mime_type: &str,
        owner_id: &str,
        folder_id: Option<&str>,
        size: u64,
        created_at: &str,
    ) {
        let payload = IndexFilePayload {
            id: id.to_string(),
            name: name.to_string(),
            mime_type: mime_type.to_string(),
            owner_id: owner_id.to_string(),
            folder_id: folder_id.unwrap_or("").to_string(),
            size,
            created_at: created_at.to_string(),
        };

        let url = format!("{}/api/v1/search/index/file", self.base_url);
        match self.http.post(&url).json(&payload).send().await {
            Ok(resp) if resp.status().is_success() => {
                tracing::debug!(file_id = %id, "search_sync_index_ok");
            }
            Ok(resp) => {
                tracing::warn!(file_id = %id, status = %resp.status(), "search_sync_index_non_ok");
            }
            Err(e) => {
                tracing::warn!(file_id = %id, error = %e, "search_sync_index_failed");
            }
        }
    }

    /// Remove a file from the search index synchronously.
    pub async fn remove_file(&self, id: &str) {
        let url = format!("{}/api/v1/search/index/file/{}", self.base_url, id);
        match self.http.delete(&url).send().await {
            Ok(resp) if resp.status().is_success() => {
                tracing::debug!(file_id = %id, "search_sync_remove_ok");
            }
            Ok(resp) => {
                tracing::warn!(file_id = %id, status = %resp.status(), "search_sync_remove_non_ok");
            }
            Err(e) => {
                tracing::warn!(file_id = %id, error = %e, "search_sync_remove_failed");
            }
        }
    }
}
