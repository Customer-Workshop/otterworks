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
    use chrono::Utc;
    use uuid::Uuid;

    #[test]
    fn share_permission_display_viewer() {
        assert_eq!(SharePermission::Viewer.to_string(), "viewer");
    }

    #[test]
    fn share_permission_display_editor() {
        assert_eq!(SharePermission::Editor.to_string(), "editor");
    }

    #[test]
    fn share_permission_from_str_viewer() {
        assert_eq!(
            SharePermission::from_str_value("viewer"),
            Some(SharePermission::Viewer)
        );
    }

    #[test]
    fn share_permission_from_str_editor() {
        assert_eq!(
            SharePermission::from_str_value("editor"),
            Some(SharePermission::Editor)
        );
    }

    #[test]
    fn share_permission_from_str_case_insensitive() {
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
    fn share_permission_from_str_invalid() {
        assert_eq!(SharePermission::from_str_value("admin"), None);
        assert_eq!(SharePermission::from_str_value(""), None);
    }

    #[test]
    fn share_permission_equality() {
        assert_eq!(SharePermission::Viewer, SharePermission::Viewer);
        assert_eq!(SharePermission::Editor, SharePermission::Editor);
        assert_ne!(SharePermission::Viewer, SharePermission::Editor);
    }

    #[test]
    fn file_metadata_serialization() {
        let now = Utc::now();
        let file = FileMetadata {
            id: Uuid::nil(),
            name: "test.txt".into(),
            mime_type: "text/plain".into(),
            size_bytes: 1024,
            s3_key: "files/test.txt".into(),
            folder_id: None,
            owner_id: Uuid::nil(),
            version: 1,
            is_trashed: false,
            created_at: now,
            updated_at: now,
        };
        let json = serde_json::to_string(&file).unwrap();
        assert!(json.contains("\"name\":\"test.txt\""));
        assert!(json.contains("\"size_bytes\":1024"));
        assert!(json.contains("\"is_trashed\":false"));
    }

    #[test]
    fn file_metadata_with_folder_id() {
        let now = Utc::now();
        let folder_id = Uuid::new_v4();
        let file = FileMetadata {
            id: Uuid::nil(),
            name: "doc.pdf".into(),
            mime_type: "application/pdf".into(),
            size_bytes: 2048,
            s3_key: "files/doc.pdf".into(),
            folder_id: Some(folder_id),
            owner_id: Uuid::nil(),
            version: 2,
            is_trashed: false,
            created_at: now,
            updated_at: now,
        };
        let json = serde_json::to_string(&file).unwrap();
        assert!(json.contains(&folder_id.to_string()));
    }

    #[test]
    fn file_metadata_deserialization_roundtrip() {
        let now = Utc::now();
        let original = FileMetadata {
            id: Uuid::new_v4(),
            name: "roundtrip.txt".into(),
            mime_type: "text/plain".into(),
            size_bytes: 512,
            s3_key: "files/roundtrip.txt".into(),
            folder_id: None,
            owner_id: Uuid::new_v4(),
            version: 1,
            is_trashed: true,
            created_at: now,
            updated_at: now,
        };
        let json = serde_json::to_string(&original).unwrap();
        let deserialized: FileMetadata = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.id, original.id);
        assert_eq!(deserialized.name, original.name);
        assert_eq!(deserialized.is_trashed, true);
    }

    #[test]
    fn folder_serialization() {
        let now = Utc::now();
        let folder = Folder {
            id: Uuid::nil(),
            name: "Documents".into(),
            parent_id: None,
            owner_id: Uuid::nil(),
            created_at: now,
            updated_at: now,
        };
        let json = serde_json::to_string(&folder).unwrap();
        assert!(json.contains("\"name\":\"Documents\""));
    }

    #[test]
    fn file_version_serialization() {
        let now = Utc::now();
        let version = FileVersion {
            file_id: Uuid::nil(),
            version: 3,
            s3_key: "files/v3/test.txt".into(),
            size_bytes: 4096,
            created_by: Uuid::nil(),
            created_at: now,
        };
        let json = serde_json::to_string(&version).unwrap();
        assert!(json.contains("\"version\":3"));
        assert!(json.contains("\"size_bytes\":4096"));
    }

    #[test]
    fn file_share_serialization() {
        let now = Utc::now();
        let share = FileShare {
            id: Uuid::nil(),
            file_id: Uuid::nil(),
            shared_with: Uuid::nil(),
            permission: SharePermission::Viewer,
            shared_by: Uuid::nil(),
            created_at: now,
        };
        let json = serde_json::to_string(&share).unwrap();
        assert!(json.contains("\"permission\":\"viewer\""));
    }

    #[test]
    fn health_response_serialization() {
        let resp = HealthResponse {
            status: "healthy".into(),
            service: "file-service".into(),
            version: "0.1.0".into(),
        };
        let json = serde_json::to_string(&resp).unwrap();
        assert!(json.contains("\"status\":\"healthy\""));
        assert!(json.contains("\"service\":\"file-service\""));
    }

    #[test]
    fn list_files_query_deserialization() {
        let json = r#"{"folder_id":null,"page":2,"page_size":25,"include_trashed":true}"#;
        let query: ListFilesQuery = serde_json::from_str(json).unwrap();
        assert_eq!(query.page, Some(2));
        assert_eq!(query.page_size, Some(25));
        assert_eq!(query.include_trashed, Some(true));
        assert!(query.folder_id.is_none());
    }

    #[test]
    fn create_folder_request_deserialization() {
        let owner_id = Uuid::new_v4();
        let json = format!(
            r#"{{"name":"My Folder","parent_id":null,"owner_id":"{}"}}"#,
            owner_id
        );
        let req: CreateFolderRequest = serde_json::from_str(&json).unwrap();
        assert_eq!(req.name, "My Folder");
        assert!(req.parent_id.is_none());
        assert_eq!(req.owner_id, owner_id);
    }

    #[test]
    fn share_file_request_deserialization() {
        let uid = Uuid::new_v4();
        let json = format!(
            r#"{{"shared_with":"{}","permission":"editor","shared_by":"{}"}}"#,
            uid, uid
        );
        let req: ShareFileRequest = serde_json::from_str(&json).unwrap();
        assert_eq!(req.permission, SharePermission::Editor);
        assert_eq!(req.shared_with, uid);
    }

    #[test]
    fn activity_item_serialization() {
        let item = ActivityItem {
            id: "act-1".into(),
            activity_type: "upload".into(),
            description: "Uploaded file.txt".into(),
            actor_name: "Alice".into(),
            resource_name: "file.txt".into(),
            resource_type: "file".into(),
            resource_id: "123".into(),
            created_at: "2024-01-01T00:00:00Z".into(),
        };
        let json = serde_json::to_string(&item).unwrap();
        assert!(json.contains("\"type\":\"upload\""));
        assert!(json.contains("\"description\":\"Uploaded file.txt\""));
    }

    #[test]
    fn list_files_response_serialization() {
        let resp = ListFilesResponse {
            files: vec![],
            total: 0,
            page: 1,
            page_size: 20,
        };
        let json = serde_json::to_string(&resp).unwrap();
        assert!(json.contains("\"total\":0"));
        assert!(json.contains("\"page\":1"));
    }
}
