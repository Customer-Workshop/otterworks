use chrono::Utc;
use uuid::Uuid;

// Pull in the library crate so we can use its public types.
use file_service::models::*;
use file_service::errors::{ErrorResponse, ServiceError};

// ── SharePermission ────────────────────────────────────────────────────

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

// ── FileMetadata Serde ────────────────────────────────────────────────

#[test]
fn file_metadata_serialization_roundtrip() {
    let now = Utc::now();
    let id = Uuid::new_v4();
    let owner = Uuid::new_v4();
    let folder = Uuid::new_v4();

    let meta = FileMetadata {
        id,
        name: "report.pdf".into(),
        mime_type: "application/pdf".into(),
        size_bytes: 2048,
        s3_key: format!("files/{id}"),
        folder_id: Some(folder),
        owner_id: owner,
        version: 1,
        is_trashed: false,
        created_at: now,
        updated_at: now,
    };

    let json = serde_json::to_string(&meta).unwrap();
    let deserialized: FileMetadata = serde_json::from_str(&json).unwrap();

    assert_eq!(deserialized.id, id);
    assert_eq!(deserialized.name, "report.pdf");
    assert_eq!(deserialized.mime_type, "application/pdf");
    assert_eq!(deserialized.size_bytes, 2048);
    assert_eq!(deserialized.folder_id, Some(folder));
    assert_eq!(deserialized.owner_id, owner);
    assert_eq!(deserialized.version, 1);
    assert!(!deserialized.is_trashed);
}

#[test]
fn file_metadata_optional_folder_id_null() {
    let now = Utc::now();
    let meta = FileMetadata {
        id: Uuid::new_v4(),
        name: "orphan.txt".into(),
        mime_type: "text/plain".into(),
        size_bytes: 100,
        s3_key: "files/orphan".into(),
        folder_id: None,
        owner_id: Uuid::new_v4(),
        version: 1,
        is_trashed: false,
        created_at: now,
        updated_at: now,
    };

    let json = serde_json::to_string(&meta).unwrap();
    assert!(json.contains("\"folder_id\":null"));
}

// ── Folder Serde ───────────────────────────────────────────────────────

#[test]
fn folder_serialization_roundtrip() {
    let now = Utc::now();
    let folder = Folder {
        id: Uuid::new_v4(),
        name: "Documents".into(),
        parent_id: None,
        owner_id: Uuid::new_v4(),
        created_at: now,
        updated_at: now,
    };

    let json = serde_json::to_string(&folder).unwrap();
    let deserialized: Folder = serde_json::from_str(&json).unwrap();
    assert_eq!(deserialized.name, "Documents");
    assert!(deserialized.parent_id.is_none());
}

// ── FileVersion Serde ──────────────────────────────────────────────────

#[test]
fn file_version_serialization() {
    let fv = FileVersion {
        file_id: Uuid::new_v4(),
        version: 3,
        s3_key: "files/v3".into(),
        size_bytes: 512,
        created_by: Uuid::new_v4(),
        created_at: Utc::now(),
    };
    let json = serde_json::to_string(&fv).unwrap();
    assert!(json.contains("\"version\":3"));
    assert!(json.contains("\"size_bytes\":512"));
}

// ── FileShare Serde ────────────────────────────────────────────────────

#[test]
fn file_share_serialization() {
    let share = FileShare {
        id: Uuid::new_v4(),
        file_id: Uuid::new_v4(),
        shared_with: Uuid::new_v4(),
        permission: SharePermission::Editor,
        shared_by: Uuid::new_v4(),
        created_at: Utc::now(),
    };
    let json = serde_json::to_string(&share).unwrap();
    assert!(json.contains("\"permission\":\"editor\""));
}

#[test]
fn share_permission_serde_roundtrip() {
    let json = serde_json::to_string(&SharePermission::Viewer).unwrap();
    assert_eq!(json, "\"viewer\"");
    let deserialized: SharePermission = serde_json::from_str(&json).unwrap();
    assert_eq!(deserialized, SharePermission::Viewer);
}

// ── HealthResponse ─────────────────────────────────────────────────────

#[test]
fn health_response_serialization() {
    let hr = HealthResponse {
        status: "healthy".into(),
        service: "file-service".into(),
        version: "0.1.0".into(),
    };
    let json = serde_json::to_string(&hr).unwrap();
    assert!(json.contains("\"status\":\"healthy\""));
    assert!(json.contains("\"service\":\"file-service\""));
}

// ── Request deserialization ────────────────────────────────────────────

#[test]
fn create_folder_request_deserialization() {
    let json = r#"{"name":"Docs","parent_id":null,"owner_id":"550e8400-e29b-41d4-a716-446655440000"}"#;
    let req: CreateFolderRequest = serde_json::from_str(json).unwrap();
    assert_eq!(req.name, "Docs");
    assert!(req.parent_id.is_none());
}

#[test]
fn move_file_request_deserialization() {
    let folder_id = Uuid::new_v4();
    let json = format!(r#"{{"folder_id":"{}"}}"#, folder_id);
    let req: MoveFileRequest = serde_json::from_str(&json).unwrap();
    assert_eq!(req.folder_id, Some(folder_id));
}

#[test]
fn rename_file_request_deserialization() {
    let json = r#"{"name":"new_name.txt"}"#;
    let req: RenameFileRequest = serde_json::from_str(json).unwrap();
    assert_eq!(req.name, "new_name.txt");
}

#[test]
fn share_file_request_deserialization() {
    let json = format!(
        r#"{{"shared_with":"{}","permission":"viewer","shared_by":"{}"}}"#,
        Uuid::new_v4(),
        Uuid::new_v4()
    );
    let req: ShareFileRequest = serde_json::from_str(&json).unwrap();
    assert_eq!(req.permission, SharePermission::Viewer);
}

#[test]
fn list_files_query_optional_fields() {
    let json = r#"{}"#;
    let q: ListFilesQuery = serde_json::from_str(json).unwrap();
    assert!(q.folder_id.is_none());
    assert!(q.owner_id.is_none());
    assert!(q.page.is_none());
    assert!(q.page_size.is_none());
    assert!(q.include_trashed.is_none());
}

// ── ErrorResponse ──────────────────────────────────────────────────────

#[test]
fn error_response_display() {
    let resp = ErrorResponse {
        error: "not_found".into(),
        message: "File not found".into(),
    };
    assert_eq!(resp.to_string(), "not_found: File not found");
}

// ── ServiceError Display ───────────────────────────────────────────────

#[test]
fn service_error_display_variants() {
    assert_eq!(
        ServiceError::FileNotFound("abc".into()).to_string(),
        "File not found: abc"
    );
    assert_eq!(
        ServiceError::FolderNotFound("xyz".into()).to_string(),
        "Folder not found: xyz"
    );
    assert_eq!(
        ServiceError::BadRequest("missing field".into()).to_string(),
        "Bad request: missing field"
    );
    assert_eq!(
        ServiceError::FileTooLarge {
            max_bytes: 100,
            actual_bytes: 200
        }
        .to_string(),
        "File too large: max 100 bytes, got 200 bytes"
    );
    assert_eq!(
        ServiceError::Unauthorized("no token".into()).to_string(),
        "Unauthorized: no token"
    );
    assert_eq!(
        ServiceError::Forbidden("not owner".into()).to_string(),
        "Forbidden: not owner"
    );
    assert_eq!(
        ServiceError::S3Error("timeout".into()).to_string(),
        "S3 error: timeout"
    );
    assert_eq!(
        ServiceError::DynamoError("throttle".into()).to_string(),
        "DynamoDB error: throttle"
    );
    assert_eq!(
        ServiceError::SnsError("bad arn".into()).to_string(),
        "SNS error: bad arn"
    );
    assert_eq!(
        ServiceError::Internal("oops".into()).to_string(),
        "Internal error: oops"
    );
}

// ── ServiceError → HTTP status mapping ─────────────────────────────────

#[actix_rt::test]
async fn service_error_http_status_codes() {
    use actix_web::ResponseError;

    let cases: Vec<(ServiceError, u16, &str)> = vec![
        (ServiceError::FileNotFound("x".into()), 404, "file_not_found"),
        (ServiceError::FolderNotFound("x".into()), 404, "folder_not_found"),
        (ServiceError::VersionNotFound("x".into()), 404, "version_not_found"),
        (ServiceError::ShareNotFound("x".into()), 404, "share_not_found"),
        (ServiceError::BadRequest("x".into()), 400, "bad_request"),
        (
            ServiceError::FileTooLarge {
                max_bytes: 10,
                actual_bytes: 20,
            },
            413,
            "file_too_large",
        ),
        (ServiceError::Unauthorized("x".into()), 401, "unauthorized"),
        (ServiceError::Forbidden("x".into()), 403, "forbidden"),
        (ServiceError::S3Error("x".into()), 500, "storage_error"),
        (ServiceError::DynamoError("x".into()), 500, "metadata_error"),
        (ServiceError::SnsError("x".into()), 500, "event_error"),
        (ServiceError::Internal("x".into()), 500, "internal_error"),
    ];

    for (error, expected_status, expected_type) in cases {
        let resp = error.error_response();
        assert_eq!(
            resp.status().as_u16(),
            expected_status,
            "wrong status for {:?}",
            expected_type
        );

        let body = actix_web::body::to_bytes(resp.into_body()).await.unwrap();
        let body_json: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(body_json["error"], expected_type);
    }
}
