use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileMetadata {
    pub id: Uuid,
    pub name: String,
    pub mime_type: String,
    pub size_bytes: u64,
    pub s3_key: String,
    pub folder_id: Option<Uuid>,
    pub owner_id: Uuid,
    pub version: u32,
    pub is_deleted: bool,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Folder {
    pub id: Uuid,
    pub name: String,
    pub parent_id: Option<Uuid>,
    pub owner_id: Uuid,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileVersion {
    pub file_id: Uuid,
    pub version: u32,
    pub s3_key: String,
    pub size_bytes: u64,
    pub created_by: Uuid,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Serialize)]
pub struct HealthResponse {
    pub status: String,
    pub service: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct UploadResponse {
    pub file: FileMetadata,
    pub upload_url: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct ListFilesQuery {
    pub folder_id: Option<Uuid>,
    pub page: Option<u32>,
    pub page_size: Option<u32>,
}

#[derive(Debug, Deserialize)]
pub struct CreateFolderRequest {
    pub name: String,
    pub parent_id: Option<Uuid>,
}
