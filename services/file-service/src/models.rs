use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

// ── File Metadata ──────────────────────────────────────────────────────

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
    pub is_trashed: bool,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Serialize)]
pub struct FileDetailResponse {
    #[serde(flatten)]
    pub file: FileMetadata,
    pub shared_with: Vec<FileShare>,
}

// ── Folder ─────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Folder {
    pub id: Uuid,
    pub name: String,
    pub parent_id: Option<Uuid>,
    pub owner_id: Uuid,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

// ── File Version ───────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileVersion {
    pub file_id: Uuid,
    pub version: u32,
    pub s3_key: String,
    pub size_bytes: u64,
    pub created_by: Uuid,
    pub created_at: DateTime<Utc>,
}

// ── File Share ─────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileShare {
    pub id: Uuid,
    pub file_id: Uuid,
    pub shared_with: Uuid,
    pub permission: SharePermission,
    pub shared_by: Uuid,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum SharePermission {
    Viewer,
    Editor,
}

impl std::fmt::Display for SharePermission {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            SharePermission::Viewer => write!(f, "viewer"),
            SharePermission::Editor => write!(f, "editor"),
        }
    }
}

impl SharePermission {
    pub fn from_str_value(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "viewer" => Some(SharePermission::Viewer),
            "editor" => Some(SharePermission::Editor),
            _ => None,
        }
    }
}

// ── Request / Response Types ───────────────────────────────────────────

#[derive(Debug, Serialize)]
pub struct HealthResponse {
    pub status: String,
    pub service: String,
    pub version: String,
}

#[derive(Debug, Serialize)]
pub struct UploadResponse {
    pub file: FileMetadata,
}

#[derive(Debug, Serialize)]
pub struct DownloadResponse {
    pub url: String,
    pub expires_in_secs: u64,
}

#[derive(Debug, Deserialize)]
pub struct ListFilesQuery {
    pub folder_id: Option<Uuid>,
    pub owner_id: Option<Uuid>,
    pub page: Option<u32>,
    pub page_size: Option<u32>,
    pub include_trashed: Option<bool>,
}

#[derive(Debug, Serialize)]
pub struct ListFilesResponse {
    pub files: Vec<FileMetadata>,
    pub total: usize,
    pub page: u32,
    pub page_size: u32,
}

#[derive(Debug, Serialize)]
pub struct ListVersionsResponse {
    pub versions: Vec<FileVersion>,
}

#[derive(Debug, Deserialize)]
pub struct ListFoldersQuery {
    pub parent_id: Option<Uuid>,
    pub owner_id: Option<Uuid>,
}

#[derive(Debug, Serialize)]
pub struct ListFoldersResponse {
    pub folders: Vec<Folder>,
}

#[derive(Debug, Deserialize)]
pub struct CreateFolderRequest {
    pub name: String,
    pub parent_id: Option<Uuid>,
    pub owner_id: Uuid,
}

#[derive(Debug, Deserialize)]
pub struct UpdateFolderRequest {
    pub name: Option<String>,
    pub parent_id: Option<Uuid>,
}

#[derive(Debug, Deserialize)]
pub struct MoveFileRequest {
    pub folder_id: Option<Uuid>,
}

#[derive(Debug, Deserialize)]
pub struct RenameFileRequest {
    pub name: String,
}

#[derive(Debug, Deserialize)]
pub struct ShareFileRequest {
    pub shared_with: Uuid,
    pub permission: SharePermission,
    pub shared_by: Uuid,
}

#[derive(Debug, Serialize)]
pub struct ShareFileResponse {
    pub share: FileShare,
}

// ── Activity ───────────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
pub struct ActivityItem {
    pub id: String,
    #[serde(rename = "type")]
    pub activity_type: String,
    pub description: String,
    pub actor_name: String,
    pub resource_name: String,
    pub resource_type: String,
    pub resource_id: String,
    pub created_at: String,
}

#[derive(Debug, Deserialize)]
pub struct ActivityQuery {
    pub limit: Option<u32>,
}

#[derive(Debug, Serialize)]
pub struct ActivityResponse {
    pub items: Vec<ActivityItem>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn share_permission_from_str_value_parses_known_values() {
        assert_eq!(
            SharePermission::from_str_value("viewer"),
            Some(SharePermission::Viewer)
        );
        assert_eq!(
            SharePermission::from_str_value("editor"),
            Some(SharePermission::Editor)
        );
    }

    #[test]
    fn share_permission_from_str_value_is_case_insensitive() {
        assert_eq!(
            SharePermission::from_str_value("VIEWER"),
            Some(SharePermission::Viewer)
        );
        assert_eq!(
            SharePermission::from_str_value("Editor"),
            Some(SharePermission::Editor)
        );
    }

    #[test]
    fn share_permission_from_str_value_rejects_unknown_values() {
        assert_eq!(SharePermission::from_str_value("owner"), None);
        assert_eq!(SharePermission::from_str_value(""), None);
    }

    #[test]
    fn share_permission_display_matches_wire_format() {
        assert_eq!(SharePermission::Viewer.to_string(), "viewer");
        assert_eq!(SharePermission::Editor.to_string(), "editor");
    }

    #[test]
    fn share_permission_serde_roundtrip_is_lowercase() {
        assert_eq!(
            serde_json::to_string(&SharePermission::Editor).unwrap(),
            "\"editor\""
        );
        let parsed: SharePermission = serde_json::from_str("\"viewer\"").unwrap();
        assert_eq!(parsed, SharePermission::Viewer);
    }

    #[test]
    fn share_permission_serde_rejects_unknown_value() {
        assert!(serde_json::from_str::<SharePermission>("\"owner\"").is_err());
    }

    #[test]
    fn file_detail_response_flattens_file_metadata() {
        let now = Utc::now();
        let file = FileMetadata {
            id: Uuid::nil(),
            name: "report.pdf".into(),
            mime_type: "application/pdf".into(),
            size_bytes: 42,
            s3_key: "files/report.pdf".into(),
            folder_id: None,
            owner_id: Uuid::nil(),
            version: 1,
            is_trashed: false,
            created_at: now,
            updated_at: now,
        };
        let detail = FileDetailResponse {
            file,
            shared_with: vec![],
        };
        let json = serde_json::to_value(&detail).unwrap();
        assert_eq!(json["name"], "report.pdf");
        assert_eq!(json["size_bytes"], 42);
        assert!(json["shared_with"].as_array().unwrap().is_empty());
        assert!(json.get("file").is_none());
    }

    #[test]
    fn activity_item_serializes_type_field() {
        let item = ActivityItem {
            id: "1".into(),
            activity_type: "upload".into(),
            description: "uploaded a file".into(),
            actor_name: "otter".into(),
            resource_name: "report.pdf".into(),
            resource_type: "file".into(),
            resource_id: "abc".into(),
            created_at: "2026-01-01T00:00:00Z".into(),
        };
        let json = serde_json::to_value(&item).unwrap();
        assert_eq!(json["type"], "upload");
        assert!(json.get("activity_type").is_none());
    }
}
