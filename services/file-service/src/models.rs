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
    use serde_json;
    use uuid::Uuid;

    // ── Helpers ─────────────────────────────────────────────────────────

    fn sample_file_metadata(folder_id: Option<Uuid>) -> FileMetadata {
        let now = Utc::now();
        FileMetadata {
            id: Uuid::new_v4(),
            name: "report.pdf".into(),
            mime_type: "application/pdf".into(),
            size_bytes: 4096,
            s3_key: "files/abc/report.pdf".into(),
            folder_id,
            owner_id: Uuid::new_v4(),
            version: 2,
            is_trashed: false,
            created_at: now,
            updated_at: now,
        }
    }

    fn sample_folder(parent_id: Option<Uuid>) -> Folder {
        let now = Utc::now();
        Folder {
            id: Uuid::new_v4(),
            name: "Documents".into(),
            parent_id,
            owner_id: Uuid::new_v4(),
            created_at: now,
            updated_at: now,
        }
    }

    fn sample_file_version() -> FileVersion {
        FileVersion {
            file_id: Uuid::new_v4(),
            version: 3,
            s3_key: "files/v3/key".into(),
            size_bytes: 2048,
            created_by: Uuid::new_v4(),
            created_at: Utc::now(),
        }
    }

    fn sample_file_share(permission: SharePermission) -> FileShare {
        FileShare {
            id: Uuid::new_v4(),
            file_id: Uuid::new_v4(),
            shared_with: Uuid::new_v4(),
            permission,
            shared_by: Uuid::new_v4(),
            created_at: Utc::now(),
        }
    }

    // ── FileMetadata serialization/deserialization ──────────────────────

    #[test]
    fn file_metadata_serialize_all_fields_present() {
        let file = sample_file_metadata(Some(Uuid::new_v4()));
        let val = serde_json::to_value(&file).unwrap();
        assert!(val.get("id").is_some());
        assert!(val.get("name").is_some());
        assert!(val.get("mime_type").is_some());
        assert!(val.get("size_bytes").is_some());
        assert!(val.get("s3_key").is_some());
        assert!(val.get("folder_id").is_some());
        assert!(val.get("owner_id").is_some());
        assert!(val.get("version").is_some());
        assert!(val.get("is_trashed").is_some());
        assert!(val.get("created_at").is_some());
        assert!(val.get("updated_at").is_some());
    }

    #[test]
    fn file_metadata_roundtrip() {
        let file = sample_file_metadata(Some(Uuid::new_v4()));
        let json = serde_json::to_string(&file).unwrap();
        let deserialized: FileMetadata = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.id, file.id);
        assert_eq!(deserialized.name, file.name);
        assert_eq!(deserialized.mime_type, file.mime_type);
        assert_eq!(deserialized.size_bytes, file.size_bytes);
        assert_eq!(deserialized.s3_key, file.s3_key);
        assert_eq!(deserialized.folder_id, file.folder_id);
        assert_eq!(deserialized.owner_id, file.owner_id);
        assert_eq!(deserialized.version, file.version);
        assert_eq!(deserialized.is_trashed, file.is_trashed);
    }

    #[test]
    fn file_metadata_folder_id_none_serializes_as_null() {
        let file = sample_file_metadata(None);
        let val = serde_json::to_value(&file).unwrap();
        assert!(val["folder_id"].is_null());
    }

    #[test]
    fn file_metadata_folder_id_some_serializes_as_string() {
        let folder_id = Uuid::new_v4();
        let file = sample_file_metadata(Some(folder_id));
        let val = serde_json::to_value(&file).unwrap();
        assert_eq!(val["folder_id"].as_str().unwrap(), folder_id.to_string());
    }

    #[test]
    fn file_metadata_deserialize_from_json_string() {
        let id = Uuid::new_v4();
        let owner = Uuid::new_v4();
        let json = format!(
            r#"{{
                "id": "{}",
                "name": "test.txt",
                "mime_type": "text/plain",
                "size_bytes": 100,
                "s3_key": "files/key",
                "folder_id": null,
                "owner_id": "{}",
                "version": 1,
                "is_trashed": false,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z"
            }}"#,
            id, owner
        );
        let file: FileMetadata = serde_json::from_str(&json).unwrap();
        assert_eq!(file.id, id);
        assert_eq!(file.name, "test.txt");
        assert!(file.folder_id.is_none());
    }

    // ── Folder serialization/deserialization ────────────────────────────

    #[test]
    fn folder_serialize_all_fields() {
        let folder = sample_folder(None);
        let val = serde_json::to_value(&folder).unwrap();
        assert!(val.get("id").is_some());
        assert!(val.get("name").is_some());
        assert!(val.get("parent_id").is_some());
        assert!(val.get("owner_id").is_some());
        assert!(val.get("created_at").is_some());
        assert!(val.get("updated_at").is_some());
    }

    #[test]
    fn folder_parent_id_none_serializes_as_null() {
        let folder = sample_folder(None);
        let val = serde_json::to_value(&folder).unwrap();
        assert!(val["parent_id"].is_null());
    }

    #[test]
    fn folder_parent_id_some() {
        let parent = Uuid::new_v4();
        let folder = sample_folder(Some(parent));
        let val = serde_json::to_value(&folder).unwrap();
        assert_eq!(val["parent_id"].as_str().unwrap(), parent.to_string());
    }

    #[test]
    fn folder_roundtrip() {
        let folder = sample_folder(Some(Uuid::new_v4()));
        let json = serde_json::to_string(&folder).unwrap();
        let deserialized: Folder = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.id, folder.id);
        assert_eq!(deserialized.name, folder.name);
        assert_eq!(deserialized.parent_id, folder.parent_id);
    }

    // ── FileVersion serialization ──────────────────────────────────────

    #[test]
    fn file_version_serialize_structure() {
        let ver = sample_file_version();
        let val = serde_json::to_value(&ver).unwrap();
        assert_eq!(val["file_id"].as_str().unwrap(), ver.file_id.to_string());
        assert_eq!(val["version"].as_u64().unwrap(), 3);
        assert_eq!(val["s3_key"].as_str().unwrap(), "files/v3/key");
        assert_eq!(val["size_bytes"].as_u64().unwrap(), 2048);
        assert!(val.get("created_by").is_some());
        assert!(val.get("created_at").is_some());
    }

    #[test]
    fn file_version_roundtrip() {
        let ver = sample_file_version();
        let json = serde_json::to_string(&ver).unwrap();
        let deserialized: FileVersion = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.file_id, ver.file_id);
        assert_eq!(deserialized.version, ver.version);
    }

    // ── FileShare serialization ────────────────────────────────────────

    #[test]
    fn file_share_serialize_viewer() {
        let share = sample_file_share(SharePermission::Viewer);
        let val = serde_json::to_value(&share).unwrap();
        assert_eq!(val["permission"].as_str().unwrap(), "viewer");
    }

    #[test]
    fn file_share_serialize_editor() {
        let share = sample_file_share(SharePermission::Editor);
        let val = serde_json::to_value(&share).unwrap();
        assert_eq!(val["permission"].as_str().unwrap(), "editor");
    }

    #[test]
    fn file_share_all_fields_present() {
        let share = sample_file_share(SharePermission::Editor);
        let val = serde_json::to_value(&share).unwrap();
        assert!(val.get("id").is_some());
        assert!(val.get("file_id").is_some());
        assert!(val.get("shared_with").is_some());
        assert!(val.get("permission").is_some());
        assert!(val.get("shared_by").is_some());
        assert!(val.get("created_at").is_some());
    }

    // ── SharePermission ────────────────────────────────────────────────

    #[test]
    fn share_permission_display_viewer() {
        assert_eq!(SharePermission::Viewer.to_string(), "viewer");
    }

    #[test]
    fn share_permission_display_editor() {
        assert_eq!(SharePermission::Editor.to_string(), "editor");
    }

    #[test]
    fn share_permission_from_str_value_lowercase() {
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
    fn share_permission_from_str_value_case_insensitive() {
        assert_eq!(
            SharePermission::from_str_value("VIEWER"),
            Some(SharePermission::Viewer)
        );
        assert_eq!(
            SharePermission::from_str_value("Editor"),
            Some(SharePermission::Editor)
        );
        assert_eq!(
            SharePermission::from_str_value("eDiToR"),
            Some(SharePermission::Editor)
        );
    }

    #[test]
    fn share_permission_from_str_value_invalid() {
        assert_eq!(SharePermission::from_str_value("invalid"), None);
        assert_eq!(SharePermission::from_str_value(""), None);
        assert_eq!(SharePermission::from_str_value("admin"), None);
    }

    #[test]
    fn share_permission_serde_lowercase() {
        let json = serde_json::to_string(&SharePermission::Viewer).unwrap();
        assert_eq!(json, "\"viewer\"");
        let json = serde_json::to_string(&SharePermission::Editor).unwrap();
        assert_eq!(json, "\"editor\"");
    }

    #[test]
    fn share_permission_serde_deserialize() {
        let viewer: SharePermission = serde_json::from_str("\"viewer\"").unwrap();
        assert_eq!(viewer, SharePermission::Viewer);
        let editor: SharePermission = serde_json::from_str("\"editor\"").unwrap();
        assert_eq!(editor, SharePermission::Editor);
    }

    // ── Request type deserialization ────────────────────────────────────

    #[test]
    fn list_files_query_all_fields() {
        let folder_id = Uuid::new_v4();
        let owner_id = Uuid::new_v4();
        let json = format!(
            r#"{{
                "folder_id": "{}",
                "owner_id": "{}",
                "page": 2,
                "page_size": 25,
                "include_trashed": true
            }}"#,
            folder_id, owner_id
        );
        let q: ListFilesQuery = serde_json::from_str(&json).unwrap();
        assert_eq!(q.folder_id.unwrap(), folder_id);
        assert_eq!(q.owner_id.unwrap(), owner_id);
        assert_eq!(q.page.unwrap(), 2);
        assert_eq!(q.page_size.unwrap(), 25);
        assert!(q.include_trashed.unwrap());
    }

    #[test]
    fn list_files_query_no_fields() {
        let q: ListFilesQuery = serde_json::from_str("{}").unwrap();
        assert!(q.folder_id.is_none());
        assert!(q.owner_id.is_none());
        assert!(q.page.is_none());
        assert!(q.page_size.is_none());
        assert!(q.include_trashed.is_none());
    }

    #[test]
    fn create_folder_request_valid() {
        let owner = Uuid::new_v4();
        let parent = Uuid::new_v4();
        let json = format!(
            r#"{{"name": "Photos", "parent_id": "{}", "owner_id": "{}"}}"#,
            parent, owner
        );
        let req: CreateFolderRequest = serde_json::from_str(&json).unwrap();
        assert_eq!(req.name, "Photos");
        assert_eq!(req.parent_id.unwrap(), parent);
        assert_eq!(req.owner_id, owner);
    }

    #[test]
    fn create_folder_request_no_parent() {
        let owner = Uuid::new_v4();
        let json = format!(r#"{{"name": "Root", "owner_id": "{}"}}"#, owner);
        let req: CreateFolderRequest = serde_json::from_str(&json).unwrap();
        assert!(req.parent_id.is_none());
    }

    #[test]
    fn update_folder_request_name_only() {
        let json = r#"{"name": "Renamed"}"#;
        let req: UpdateFolderRequest = serde_json::from_str(json).unwrap();
        assert_eq!(req.name.unwrap(), "Renamed");
        assert!(req.parent_id.is_none());
    }

    #[test]
    fn update_folder_request_parent_id_only() {
        let parent = Uuid::new_v4();
        let json = format!(r#"{{"parent_id": "{}"}}"#, parent);
        let req: UpdateFolderRequest = serde_json::from_str(&json).unwrap();
        assert!(req.name.is_none());
        assert_eq!(req.parent_id.unwrap(), parent);
    }

    #[test]
    fn update_folder_request_both_fields() {
        let parent = Uuid::new_v4();
        let json = format!(r#"{{"name": "New", "parent_id": "{}"}}"#, parent);
        let req: UpdateFolderRequest = serde_json::from_str(&json).unwrap();
        assert_eq!(req.name.unwrap(), "New");
        assert_eq!(req.parent_id.unwrap(), parent);
    }

    #[test]
    fn move_file_request_with_folder() {
        let fid = Uuid::new_v4();
        let json = format!(r#"{{"folder_id": "{}"}}"#, fid);
        let req: MoveFileRequest = serde_json::from_str(&json).unwrap();
        assert_eq!(req.folder_id.unwrap(), fid);
    }

    #[test]
    fn move_file_request_without_folder() {
        let req: MoveFileRequest = serde_json::from_str("{}").unwrap();
        assert!(req.folder_id.is_none());
    }

    #[test]
    fn rename_file_request_valid() {
        let json = r#"{"name": "new_name.txt"}"#;
        let req: RenameFileRequest = serde_json::from_str(json).unwrap();
        assert_eq!(req.name, "new_name.txt");
    }

    #[test]
    fn share_file_request_valid() {
        let user = Uuid::new_v4();
        let by = Uuid::new_v4();
        let json = format!(
            r#"{{"shared_with": "{}", "permission": "editor", "shared_by": "{}"}}"#,
            user, by
        );
        let req: ShareFileRequest = serde_json::from_str(&json).unwrap();
        assert_eq!(req.shared_with, user);
        assert_eq!(req.permission, SharePermission::Editor);
        assert_eq!(req.shared_by, by);
    }

    #[test]
    fn share_file_request_viewer() {
        let user = Uuid::new_v4();
        let by = Uuid::new_v4();
        let json = format!(
            r#"{{"shared_with": "{}", "permission": "viewer", "shared_by": "{}"}}"#,
            user, by
        );
        let req: ShareFileRequest = serde_json::from_str(&json).unwrap();
        assert_eq!(req.permission, SharePermission::Viewer);
    }

    // ── Response type serialization ────────────────────────────────────

    #[test]
    fn health_response_serialize() {
        let resp = HealthResponse {
            status: "ok".into(),
            service: "file-service".into(),
            version: "0.1.0".into(),
        };
        let val = serde_json::to_value(&resp).unwrap();
        assert_eq!(val["status"], "ok");
        assert_eq!(val["service"], "file-service");
        assert_eq!(val["version"], "0.1.0");
    }

    #[test]
    fn upload_response_serialize() {
        let file = sample_file_metadata(None);
        let resp = UploadResponse { file };
        let val = serde_json::to_value(&resp).unwrap();
        assert!(val.get("file").is_some());
        assert!(val["file"].get("id").is_some());
    }

    #[test]
    fn download_response_serialize() {
        let resp = DownloadResponse {
            url: "https://s3.example.com/presigned".into(),
            expires_in_secs: 3600,
        };
        let val = serde_json::to_value(&resp).unwrap();
        assert_eq!(val["url"], "https://s3.example.com/presigned");
        assert_eq!(val["expires_in_secs"], 3600);
    }

    #[test]
    fn list_files_response_serialize() {
        let resp = ListFilesResponse {
            files: vec![sample_file_metadata(None)],
            total: 1,
            page: 1,
            page_size: 20,
        };
        let val = serde_json::to_value(&resp).unwrap();
        assert_eq!(val["total"], 1);
        assert_eq!(val["page"], 1);
        assert_eq!(val["page_size"], 20);
        assert_eq!(val["files"].as_array().unwrap().len(), 1);
    }

    #[test]
    fn list_folders_response_serialize() {
        let resp = ListFoldersResponse {
            folders: vec![sample_folder(None), sample_folder(Some(Uuid::new_v4()))],
        };
        let val = serde_json::to_value(&resp).unwrap();
        assert_eq!(val["folders"].as_array().unwrap().len(), 2);
    }

    #[test]
    fn list_versions_response_serialize() {
        let resp = ListVersionsResponse {
            versions: vec![sample_file_version()],
        };
        let val = serde_json::to_value(&resp).unwrap();
        assert_eq!(val["versions"].as_array().unwrap().len(), 1);
    }

    #[test]
    fn activity_item_type_rename() {
        let item = ActivityItem {
            id: "act-1".into(),
            activity_type: "file_upload".into(),
            description: "Uploaded report.pdf".into(),
            actor_name: "Alice".into(),
            resource_name: "report.pdf".into(),
            resource_type: "file".into(),
            resource_id: Uuid::new_v4().to_string(),
            created_at: Utc::now().to_rfc3339(),
        };
        let val = serde_json::to_value(&item).unwrap();
        assert_eq!(val["type"], "file_upload");
        assert!(val.get("activity_type").is_none());
        assert_eq!(val["description"], "Uploaded report.pdf");
        assert_eq!(val["actor_name"], "Alice");
    }

    #[test]
    fn activity_response_serialize() {
        let resp = ActivityResponse {
            items: vec![
                ActivityItem {
                    id: "a1".into(),
                    activity_type: "file_upload".into(),
                    description: "Uploaded".into(),
                    actor_name: "Bob".into(),
                    resource_name: "file.txt".into(),
                    resource_type: "file".into(),
                    resource_id: "r1".into(),
                    created_at: "2024-01-01T00:00:00Z".into(),
                },
                ActivityItem {
                    id: "a2".into(),
                    activity_type: "file_delete".into(),
                    description: "Deleted".into(),
                    actor_name: "Carol".into(),
                    resource_name: "old.txt".into(),
                    resource_type: "file".into(),
                    resource_id: "r2".into(),
                    created_at: "2024-01-02T00:00:00Z".into(),
                },
            ],
        };
        let val = serde_json::to_value(&resp).unwrap();
        let items = val["items"].as_array().unwrap();
        assert_eq!(items.len(), 2);
        assert_eq!(items[0]["type"], "file_upload");
        assert_eq!(items[1]["type"], "file_delete");
    }
}
