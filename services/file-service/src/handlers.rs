use actix_multipart::Multipart;
use actix_web::{web, HttpRequest, HttpResponse};
use bytes::BytesMut;
use chrono::Utc;
use futures_util::StreamExt;
use uuid::Uuid;

async fn chaos_active(cm: &mut redis::aio::ConnectionManager, flag: &str) -> bool {
    let result: redis::RedisResult<i64> = redis::cmd("EXISTS").arg(flag).query_async(cm).await;
    result.unwrap_or(0) > 0
}

use crate::config::AppConfig;
use crate::errors::ServiceError;
use crate::events::EventPublisher;
use crate::metadata::MetadataClient;
use crate::middleware;
use crate::models::{
    ActivityItem, ActivityQuery, ActivityResponse, BulkActionRequest, BulkActionResponse,
    BulkDownloadResponse, BulkDownloadUrl, BulkItemError, BulkMoveRequest, CreateFolderRequest,
    DownloadResponse, FileDetailResponse, FileMetadata, FileShare, FileVersion, Folder,
    HealthResponse, ListFilesQuery, ListFilesResponse, ListFoldersQuery, ListFoldersResponse,
    ListVersionsResponse, MoveFileRequest, RenameFileRequest, ShareFileRequest, ShareFileResponse,
    UpdateFolderRequest, UploadResponse,
};
use crate::storage::S3Client;

// -- Health & Metrics --

pub async fn health() -> HttpResponse {
    HttpResponse::Ok().json(HealthResponse {
        status: "healthy".into(),
        service: "file-service".into(),
        version: env!("CARGO_PKG_VERSION").into(),
    })
}

pub async fn metrics() -> HttpResponse {
    HttpResponse::Ok()
        .content_type("text/plain; charset=utf-8")
        .body(middleware::render_metrics())
}

// -- File Handlers --

pub async fn upload_file(
    req: HttpRequest,
    s3: web::Data<S3Client>,
    meta: web::Data<MetadataClient>,
    events: web::Data<EventPublisher>,
    config: web::Data<AppConfig>,
    redis_cm: web::Data<redis::aio::ConnectionManager>,
    mut payload: Multipart,
) -> Result<HttpResponse, ServiceError> {
    // Prefer owner_id from X-User-ID header (injected by api-gateway from JWT).
    // Fall back to the multipart field for direct/internal callers.
    let header_owner_id = req
        .headers()
        .get("X-User-ID")
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.trim().parse::<Uuid>().ok());

    let mut file_bytes = BytesMut::new();
    let mut file_name = String::from("unnamed");
    let mut content_type = String::from("application/octet-stream");
    let mut owner_id: Option<Uuid> = None;
    let mut folder_id: Option<Uuid> = None;

    while let Some(item) = payload.next().await {
        let mut field = item.map_err(|e| ServiceError::BadRequest(e.to_string()))?;
        let disposition = field.content_disposition().cloned();
        let field_name = disposition
            .as_ref()
            .and_then(|d| d.get_name().map(|s| s.to_string()))
            .unwrap_or_default();

        match field_name.as_str() {
            "file" => {
                if let Some(fname) = disposition.as_ref().and_then(|d| d.get_filename()) {
                    file_name = fname.to_string();
                }
                if let Some(ct) = field.content_type() {
                    content_type = ct.to_string();
                }
                while let Some(chunk) = field.next().await {
                    let data = chunk.map_err(|e| ServiceError::BadRequest(e.to_string()))?;
                    file_bytes.extend_from_slice(&data);
                    if file_bytes.len() as u64 > config.server.max_upload_bytes {
                        return Err(ServiceError::FileTooLarge {
                            max_bytes: config.server.max_upload_bytes,
                            actual_bytes: file_bytes.len() as u64,
                        });
                    }
                }
            }
            "owner_id" => {
                let mut value = BytesMut::new();
                while let Some(chunk) = field.next().await {
                    let data = chunk.map_err(|e| ServiceError::BadRequest(e.to_string()))?;
                    value.extend_from_slice(&data);
                }
                let s = String::from_utf8_lossy(&value).to_string();
                owner_id = Some(
                    s.trim()
                        .parse::<Uuid>()
                        .map_err(|e| ServiceError::BadRequest(format!("invalid owner_id: {e}")))?,
                );
            }
            "folder_id" => {
                let mut value = BytesMut::new();
                while let Some(chunk) = field.next().await {
                    let data = chunk.map_err(|e| ServiceError::BadRequest(e.to_string()))?;
                    value.extend_from_slice(&data);
                }
                let s = String::from_utf8_lossy(&value).to_string();
                let trimmed = s.trim();
                if !trimmed.is_empty() {
                    folder_id = Some(trimmed.parse::<Uuid>().map_err(|e| {
                        ServiceError::BadRequest(format!("invalid folder_id: {e}"))
                    })?);
                }
            }
            _ => {}
        }
    }

    let owner = header_owner_id
        .or(owner_id)
        .ok_or_else(|| ServiceError::BadRequest("owner_id is required".into()))?;

    if file_bytes.is_empty() {
        return Err(ServiceError::BadRequest("file field is required".into()));
    }

    let file_id = Uuid::new_v4();
    let s3_key = format!("files/{}/{}", owner, file_id);
    let now = Utc::now();
    let size = file_bytes.len() as u64;

    // CHAOS: when this flag is active the S3 client targets a nonexistent
    // bucket, simulating a misconfigured bucket name after a recent infra
    // change.  The AWS SDK returns NoSuchBucket which surfaces as a 500.
    let effective_bucket = if chaos_active(
        &mut redis_cm.get_ref().clone(),
        "chaos:file-service:upload_s3_error",
    )
    .await
    {
        tracing::warn!("Chaos flag active: redirecting upload to nonexistent bucket");
        "otterworks-files-chaos-nonexistent".to_string()
    } else {
        s3.bucket.clone()
    };
    let chaos_s3 = crate::storage::S3Client {
        client: s3.client.clone(),
        bucket: effective_bucket,
    };
    chaos_s3
        .upload_object(&s3_key, file_bytes.freeze(), &content_type)
        .await?;

    let file_meta = FileMetadata {
        id: file_id,
        name: file_name,
        mime_type: content_type,
        size_bytes: size,
        s3_key: s3_key.clone(),
        folder_id,
        owner_id: owner,
        version: 1,
        is_trashed: false,
        created_at: now,
        updated_at: now,
    };

    meta.put_file(&file_meta).await?;

    let version = FileVersion {
        file_id,
        version: 1,
        s3_key,
        size_bytes: size,
        created_by: owner,
        created_at: now,
    };
    meta.put_version(&version).await?;

    let _ = events
        .file_uploaded(
            &file_id,
            &owner,
            folder_id.as_ref(),
            &file_meta.name,
            &file_meta.mime_type,
            file_meta.size_bytes,
        )
        .await;

    tracing::info!(file_id = %file_id, name = %file_meta.name, size = %size, "File uploaded");

    Ok(HttpResponse::Created().json(UploadResponse { file: file_meta }))
}

pub async fn get_file_metadata(
    meta: web::Data<MetadataClient>,
    path: web::Path<String>,
) -> Result<HttpResponse, ServiceError> {
    let file_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid file id: {e}")))?;
    let file = meta.get_file(&file_id).await?;
    let shares = meta.list_shares(&file_id).await.unwrap_or_default();
    Ok(HttpResponse::Ok().json(FileDetailResponse {
        file,
        shared_with: shares,
    }))
}

/// Resolve the effective owner_id for list operations.
///
/// Prefer the `X-User-ID` header injected by the api-gateway from the
/// authenticated JWT. This prevents a caller from spoofing another user's
/// `owner_id` via the query string. Fall back to `query.owner_id` only when
/// no header is present (direct/internal callers).
fn resolve_owner_id(req: &HttpRequest, query_owner_id: Option<Uuid>) -> Option<Uuid> {
    let header_owner_id = req
        .headers()
        .get("X-User-ID")
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.trim().parse::<Uuid>().ok());

    header_owner_id.or(query_owner_id)
}

pub async fn list_files(
    req: HttpRequest,
    meta: web::Data<MetadataClient>,
    query: web::Query<ListFilesQuery>,
) -> Result<HttpResponse, ServiceError> {
    let include_trashed = query.include_trashed.unwrap_or(false);
    let owner_id = resolve_owner_id(&req, query.owner_id);
    let files = meta
        .list_files(query.folder_id, owner_id, include_trashed)
        .await?;

    let page = query.page.unwrap_or(1).max(1);
    let page_size = query.page_size.unwrap_or(50).min(100);
    let total = files.len();
    let start = (page - 1).saturating_mul(page_size) as usize;
    let paged: Vec<FileMetadata> = files
        .into_iter()
        .skip(start)
        .take(page_size as usize)
        .collect();

    Ok(HttpResponse::Ok().json(ListFilesResponse {
        files: paged,
        total,
        page,
        page_size,
    }))
}

pub async fn list_shared_files(
    meta: web::Data<MetadataClient>,
    req: HttpRequest,
    query: web::Query<ListFilesQuery>,
) -> Result<HttpResponse, ServiceError> {
    let user_id: Uuid = req
        .headers()
        .get("X-User-ID")
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.parse().ok())
        .ok_or_else(|| ServiceError::BadRequest("missing X-User-ID header".into()))?;

    let shares = meta.list_shares_for_user(&user_id).await?;

    // Deduplicate by file_id to handle legacy duplicate share records
    let mut seen_file_ids = std::collections::HashSet::new();
    let mut files = Vec::new();
    for share in &shares {
        if !seen_file_ids.insert(share.file_id) {
            continue;
        }
        match meta.get_file(&share.file_id).await {
            Ok(file) if !file.is_trashed => files.push(file),
            _ => {}
        }
    }

    let page = query.page.unwrap_or(1).max(1);
    let page_size = query.page_size.unwrap_or(50).min(100);
    let total = files.len();
    let start = (page - 1).saturating_mul(page_size) as usize;
    let paged: Vec<FileMetadata> = files
        .into_iter()
        .skip(start)
        .take(page_size as usize)
        .collect();

    Ok(HttpResponse::Ok().json(ListFilesResponse {
        files: paged,
        total,
        page,
        page_size,
    }))
}

pub async fn list_trashed(
    req: HttpRequest,
    meta: web::Data<MetadataClient>,
    query: web::Query<ListFilesQuery>,
) -> Result<HttpResponse, ServiceError> {
    let owner_id = resolve_owner_id(&req, query.owner_id);
    let files = meta.list_trashed(owner_id).await?;

    let page = query.page.unwrap_or(1).max(1);
    let page_size = query.page_size.unwrap_or(50).min(100);
    let total = files.len();
    let start = (page - 1).saturating_mul(page_size) as usize;
    let paged: Vec<FileMetadata> = files
        .into_iter()
        .skip(start)
        .take(page_size as usize)
        .collect();

    Ok(HttpResponse::Ok().json(ListFilesResponse {
        files: paged,
        total,
        page,
        page_size,
    }))
}
pub async fn delete_file(
    s3: web::Data<S3Client>,
    meta: web::Data<MetadataClient>,
    events: web::Data<EventPublisher>,
    path: web::Path<String>,
) -> Result<HttpResponse, ServiceError> {
    let file_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid file id: {e}")))?;

    let file = meta.get_file(&file_id).await?;
    meta.delete_file(&file_id).await?;
    s3.delete_object(&file.s3_key).await?;

    let _ = events.file_deleted(&file_id, &file.owner_id).await;

    tracing::info!(file_id = %file_id, "File deleted");
    Ok(HttpResponse::NoContent().finish())
}

pub async fn download_file(
    s3: web::Data<S3Client>,
    meta: web::Data<MetadataClient>,
    path: web::Path<String>,
) -> Result<HttpResponse, ServiceError> {
    let file_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid file id: {e}")))?;

    let file = meta.get_file(&file_id).await?;
    let url = s3.presigned_download_url(&file.s3_key, 3600).await?;

    Ok(HttpResponse::Ok().json(DownloadResponse {
        url,
        expires_in_secs: 3600,
    }))
}

pub async fn move_file(
    meta: web::Data<MetadataClient>,
    events: web::Data<EventPublisher>,
    path: web::Path<String>,
    body: web::Json<MoveFileRequest>,
) -> Result<HttpResponse, ServiceError> {
    let file_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid file id: {e}")))?;

    let file = meta.move_file(&file_id, body.folder_id).await?;

    let _ = events
        .file_moved(&file_id, &file.owner_id, body.folder_id.as_ref())
        .await;

    tracing::info!(file_id = %file_id, folder_id = ?body.folder_id, "File moved");
    Ok(HttpResponse::Ok().json(file))
}

pub async fn rename_file(
    meta: web::Data<MetadataClient>,
    events: web::Data<EventPublisher>,
    path: web::Path<String>,
    body: web::Json<RenameFileRequest>,
) -> Result<HttpResponse, ServiceError> {
    let file_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid file id: {e}")))?;

    let name = body.name.trim();
    if name.is_empty() {
        return Err(ServiceError::BadRequest("name cannot be empty".into()));
    }

    let file = meta.rename_file(&file_id, name).await?;

    let _ = events
        .file_updated(
            &file_id,
            &file.owner_id,
            file.folder_id.as_ref(),
            &file.name,
            &file.mime_type,
            file.size_bytes as u64,
        )
        .await;

    tracing::info!(file_id = %file_id, new_name = %name, "File renamed");
    Ok(HttpResponse::Ok().json(file))
}

pub async fn list_versions(
    meta: web::Data<MetadataClient>,
    path: web::Path<String>,
) -> Result<HttpResponse, ServiceError> {
    let file_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid file id: {e}")))?;

    let versions = meta.list_versions(&file_id).await?;
    Ok(HttpResponse::Ok().json(ListVersionsResponse { versions }))
}

pub async fn trash_file(
    meta: web::Data<MetadataClient>,
    events: web::Data<EventPublisher>,
    path: web::Path<String>,
) -> Result<HttpResponse, ServiceError> {
    let file_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid file id: {e}")))?;

    let file = meta.trash_file(&file_id).await?;

    let _ = events.file_trashed(&file_id, &file.owner_id).await;

    tracing::info!(file_id = %file_id, "File trashed");
    Ok(HttpResponse::Ok().json(file))
}

pub async fn restore_file(
    meta: web::Data<MetadataClient>,
    events: web::Data<EventPublisher>,
    path: web::Path<String>,
) -> Result<HttpResponse, ServiceError> {
    let file_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid file id: {e}")))?;

    let file = meta.restore_file(&file_id).await?;

    let _ = events
        .file_restored(
            &file_id,
            &file.owner_id,
            file.folder_id.as_ref(),
            &file.name,
            &file.mime_type,
            file.size_bytes as u64,
        )
        .await;

    tracing::info!(file_id = %file_id, "File restored");
    Ok(HttpResponse::Ok().json(file))
}

pub async fn share_file(
    meta: web::Data<MetadataClient>,
    events: web::Data<EventPublisher>,
    path: web::Path<String>,
    body: web::Json<ShareFileRequest>,
) -> Result<HttpResponse, ServiceError> {
    let file_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid file id: {e}")))?;

    // Ensure file exists
    let file = meta.get_file(&file_id).await?;

    // Check if share already exists for this file + user
    if let Some(existing) = meta
        .find_existing_share(&file_id, &body.shared_with)
        .await?
    {
        // Update permission if different, otherwise return existing
        if existing.permission != body.permission {
            let updated = FileShare {
                id: existing.id,
                file_id,
                shared_with: body.shared_with,
                permission: body.permission.clone(),
                shared_by: body.shared_by,
                created_at: existing.created_at,
            };
            meta.put_share(&updated).await?;
            tracing::info!(file_id = %file_id, shared_with = %body.shared_with, "File share updated");
            return Ok(HttpResponse::Ok().json(ShareFileResponse { share: updated }));
        }
        tracing::info!(file_id = %file_id, shared_with = %body.shared_with, "File already shared");
        return Ok(HttpResponse::Ok().json(ShareFileResponse { share: existing }));
    }

    let share = FileShare {
        id: Uuid::new_v4(),
        file_id,
        shared_with: body.shared_with,
        permission: body.permission.clone(),
        shared_by: body.shared_by,
        created_at: Utc::now(),
    };

    meta.put_share(&share).await?;

    let _ = events
        .file_shared(&file_id, &file.owner_id, &body.shared_with)
        .await;

    tracing::info!(file_id = %file_id, shared_with = %body.shared_with, "File shared");
    Ok(HttpResponse::Created().json(ShareFileResponse { share }))
}

pub async fn remove_share(
    meta: web::Data<MetadataClient>,
    path: web::Path<(String, String)>,
) -> Result<HttpResponse, ServiceError> {
    let (file_id_str, user_id_str) = path.into_inner();
    let file_id: Uuid = file_id_str
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid file id: {e}")))?;
    let user_id: Uuid = user_id_str
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid user id: {e}")))?;

    // Ensure file exists
    let _file = meta.get_file(&file_id).await?;

    // Find the existing share
    let share = meta
        .find_existing_share(&file_id, &user_id)
        .await?
        .ok_or_else(|| ServiceError::ShareNotFound("Share not found".into()))?;

    meta.delete_share(&share.id).await?;

    tracing::info!(file_id = %file_id, user_id = %user_id, "File share removed");
    Ok(HttpResponse::NoContent().finish())
}

// -- Folder Handlers --

pub async fn list_folders(
    req: HttpRequest,
    meta: web::Data<MetadataClient>,
    query: web::Query<ListFoldersQuery>,
) -> Result<HttpResponse, ServiceError> {
    let owner_id = resolve_owner_id(&req, query.owner_id);
    let folders = meta.list_folders(query.parent_id, owner_id).await?;
    Ok(HttpResponse::Ok().json(ListFoldersResponse { folders }))
}

pub async fn create_folder(
    meta: web::Data<MetadataClient>,
    body: web::Json<CreateFolderRequest>,
) -> Result<HttpResponse, ServiceError> {
    let now = Utc::now();
    let folder = Folder {
        id: Uuid::new_v4(),
        name: body.name.clone(),
        parent_id: body.parent_id,
        owner_id: body.owner_id,
        created_at: now,
        updated_at: now,
    };

    meta.put_folder(&folder).await?;
    tracing::info!(folder_id = %folder.id, name = %folder.name, "Folder created");
    Ok(HttpResponse::Created().json(folder))
}

pub async fn get_folder(
    meta: web::Data<MetadataClient>,
    path: web::Path<String>,
) -> Result<HttpResponse, ServiceError> {
    let folder_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid folder id: {e}")))?;

    let folder = meta.get_folder(&folder_id).await?;
    Ok(HttpResponse::Ok().json(folder))
}

pub async fn update_folder(
    meta: web::Data<MetadataClient>,
    path: web::Path<String>,
    body: web::Json<UpdateFolderRequest>,
) -> Result<HttpResponse, ServiceError> {
    let folder_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid folder id: {e}")))?;

    let folder = meta
        .update_folder(&folder_id, body.name.clone(), body.parent_id)
        .await?;
    Ok(HttpResponse::Ok().json(folder))
}

pub async fn delete_folder(
    meta: web::Data<MetadataClient>,
    path: web::Path<String>,
) -> Result<HttpResponse, ServiceError> {
    let folder_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid folder id: {e}")))?;

    meta.delete_folder(&folder_id).await?;
    tracing::info!(folder_id = %folder_id, "Folder deleted");
    Ok(HttpResponse::NoContent().finish())
}

// -- Bulk Operation Handlers --

pub async fn bulk_trash(
    meta: web::Data<MetadataClient>,
    events: web::Data<EventPublisher>,
    body: web::Json<BulkActionRequest>,
) -> Result<HttpResponse, ServiceError> {
    let mut succeeded: u32 = 0;
    let mut failed: u32 = 0;
    let mut errors: Vec<BulkItemError> = Vec::new();

    for file_id in &body.file_ids {
        match meta.trash_file(file_id).await {
            Ok(file) => {
                let _ = events.file_trashed(file_id, &file.owner_id).await;
                succeeded += 1;
            }
            Err(e) => {
                failed += 1;
                errors.push(BulkItemError {
                    id: file_id.to_string(),
                    error: e.to_string(),
                });
            }
        }
    }

    if let Some(folder_ids) = &body.folder_ids {
        for folder_id in folder_ids {
            match meta.delete_folder(folder_id).await {
                Ok(()) => {
                    succeeded += 1;
                }
                Err(e) => {
                    failed += 1;
                    errors.push(BulkItemError {
                        id: folder_id.to_string(),
                        error: e.to_string(),
                    });
                }
            }
        }
    }

    tracing::info!(succeeded = succeeded, failed = failed, "Bulk trash completed");
    Ok(HttpResponse::Ok().json(BulkActionResponse {
        succeeded,
        failed,
        errors,
    }))
}

pub async fn bulk_move(
    meta: web::Data<MetadataClient>,
    events: web::Data<EventPublisher>,
    body: web::Json<BulkMoveRequest>,
) -> Result<HttpResponse, ServiceError> {
    let mut succeeded: u32 = 0;
    let mut failed: u32 = 0;
    let mut errors: Vec<BulkItemError> = Vec::new();

    for file_id in &body.file_ids {
        match meta.move_file(file_id, body.target_folder_id).await {
            Ok(file) => {
                let _ = events
                    .file_moved(file_id, &file.owner_id, body.target_folder_id.as_ref())
                    .await;
                succeeded += 1;
            }
            Err(e) => {
                failed += 1;
                errors.push(BulkItemError {
                    id: file_id.to_string(),
                    error: e.to_string(),
                });
            }
        }
    }

    tracing::info!(succeeded = succeeded, failed = failed, "Bulk move completed");
    Ok(HttpResponse::Ok().json(BulkActionResponse {
        succeeded,
        failed,
        errors,
    }))
}

pub async fn bulk_download(
    s3: web::Data<S3Client>,
    meta: web::Data<MetadataClient>,
    body: web::Json<BulkActionRequest>,
) -> Result<HttpResponse, ServiceError> {
    let mut urls: Vec<BulkDownloadUrl> = Vec::new();

    for file_id in &body.file_ids {
        let file = meta.get_file(file_id).await?;
        let url = s3.presigned_download_url(&file.s3_key, 3600).await?;
        urls.push(BulkDownloadUrl {
            file_id: file_id.to_string(),
            name: file.name,
            url,
            expires_in_secs: 3600,
        });
    }

    Ok(HttpResponse::Ok().json(BulkDownloadResponse { urls }))
}

// -- Activity Handler --

pub async fn list_activity(
    req: HttpRequest,
    meta: web::Data<MetadataClient>,
    query: web::Query<ActivityQuery>,
) -> Result<HttpResponse, ServiceError> {
    let owner_id = req
        .headers()
        .get("X-User-ID")
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.trim().parse::<Uuid>().ok())
        .ok_or_else(|| ServiceError::BadRequest("missing owner context".into()))?;

    let limit = query.limit.unwrap_or(20).min(50) as usize;

    let (files, shares) = futures_util::future::join(
        meta.list_files(None, Some(owner_id), true),
        meta.list_shares_by_owner(&owner_id),
    )
    .await;

    let files = files.unwrap_or_default();
    let shares = shares.unwrap_or_default();

    // Build a file-id → name lookup for share descriptions
    let file_names: std::collections::HashMap<Uuid, String> =
        files.iter().map(|f| (f.id, f.name.clone())).collect();

    let mut items: Vec<ActivityItem> = Vec::new();

    for f in &files {
        items.push(ActivityItem {
            id: format!("upload-{}", f.id),
            activity_type: "upload".into(),
            description: format!("Uploaded {}", f.name),
            actor_name: "You".into(),
            resource_name: f.name.clone(),
            resource_type: "file".into(),
            resource_id: f.id.to_string(),
            created_at: f.created_at.to_rfc3339(),
        });
    }

    for s in &shares {
        let name = file_names
            .get(&s.file_id)
            .cloned()
            .unwrap_or_else(|| "a file".into());
        items.push(ActivityItem {
            id: format!("share-{}", s.id),
            activity_type: "share".into(),
            description: format!("Shared {}", name),
            actor_name: "You".into(),
            resource_name: name,
            resource_type: "file".into(),
            resource_id: s.file_id.to_string(),
            created_at: s.created_at.to_rfc3339(),
        });
    }

    items.sort_by(|a, b| b.created_at.cmp(&a.created_at));
    items.truncate(limit);

    Ok(HttpResponse::Ok().json(ActivityResponse { items }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use actix_web::test;

    #[actix_rt::test]
    async fn test_health_endpoint() {
        let resp = health().await;
        assert_eq!(resp.status(), actix_web::http::StatusCode::OK);
    }

    #[actix_rt::test]
    async fn test_metrics_endpoint() {
        let resp = metrics().await;
        assert_eq!(resp.status(), actix_web::http::StatusCode::OK);
    }

    // -- Bulk operation integration tests --
    //
    // These tests spin up an actix-web test server wired to LocalStack
    // (DynamoDB, S3, SNS). They require the same environment variables as the
    // service itself (AWS_ENDPOINT_URL, etc.).  When those aren't available the
    // tests are silently skipped so `cargo test` still passes in bare CI
    // environments.

    async fn build_test_app() -> Option<(
        actix_web::test::TestServer,
        web::Data<MetadataClient>,
        web::Data<S3Client>,
    )> {
        dotenvy::dotenv().ok();

        let config = match std::panic::catch_unwind(crate::config::AppConfig::from_env) {
            Ok(c) => c,
            Err(_) => return None,
        };

        let s3 = crate::storage::S3Client::new(&config.aws).await;
        let meta = crate::metadata::MetadataClient::new(&config.aws).await;
        let events = crate::events::EventPublisher::new(&config.sns, &config.aws).await;

        let s3_data = web::Data::new(s3);
        let meta_data = web::Data::new(meta);
        let events_data = web::Data::new(events);

        let s3_ret = s3_data.clone();
        let meta_ret = meta_data.clone();

        let srv = actix_web::test::start(move || {
            actix_web::App::new()
                .app_data(s3_data.clone())
                .app_data(meta_data.clone())
                .app_data(events_data.clone())
                .service(
                    web::scope("/api/v1/files")
                        .route("/bulk/trash", web::post().to(bulk_trash))
                        .route("/bulk/move", web::post().to(bulk_move))
                        .route("/bulk/download", web::post().to(bulk_download)),
                )
        });
        Some((srv, meta_ret, s3_ret))
    }

    async fn seed_file(
        meta: &MetadataClient,
        s3: &S3Client,
    ) -> FileMetadata {
        let id = Uuid::new_v4();
        let owner = Uuid::new_v4();
        let now = chrono::Utc::now();
        let s3_key = format!("files/{}/{}", owner, id);

        s3.upload_object(&s3_key, bytes::Bytes::from("test-content"), "text/plain")
            .await
            .expect("seed s3 upload");

        let file = FileMetadata {
            id,
            name: format!("test-{}.txt", &id.to_string()[..8]),
            mime_type: "text/plain".into(),
            size_bytes: 12,
            s3_key,
            folder_id: None,
            owner_id: owner,
            version: 1,
            is_trashed: false,
            created_at: now,
            updated_at: now,
        };
        meta.put_file(&file).await.expect("seed put_file");
        file
    }

    #[actix_rt::test]
    async fn test_bulk_trash_happy_path() {
        let Some((srv, meta, s3)) = build_test_app().await else {
            eprintln!("Skipping test_bulk_trash_happy_path: env not available");
            return;
        };
        let f1 = seed_file(&meta, &s3).await;
        let f2 = seed_file(&meta, &s3).await;

        let payload = serde_json::json!({
            "file_ids": [f1.id.to_string(), f2.id.to_string()]
        });
        let mut resp = srv
            .post("/api/v1/files/bulk/trash")
            .send_json(&payload)
            .await
            .unwrap();
        assert_eq!(resp.status(), actix_web::http::StatusCode::OK);

        let body: BulkActionResponse = resp.json().await.unwrap();
        assert_eq!(body.succeeded, 2);
        assert_eq!(body.failed, 0);
        assert!(body.errors.is_empty());

        let trashed1 = meta.get_file(&f1.id).await.unwrap();
        assert!(trashed1.is_trashed);
        let trashed2 = meta.get_file(&f2.id).await.unwrap();
        assert!(trashed2.is_trashed);
    }

    #[actix_rt::test]
    async fn test_bulk_trash_partial_failure() {
        let Some((srv, meta, s3)) = build_test_app().await else {
            eprintln!("Skipping test_bulk_trash_partial_failure: env not available");
            return;
        };
        let f1 = seed_file(&meta, &s3).await;
        let bad_id = Uuid::new_v4();

        let payload = serde_json::json!({
            "file_ids": [f1.id.to_string(), bad_id.to_string()]
        });
        let mut resp = srv
            .post("/api/v1/files/bulk/trash")
            .send_json(&payload)
            .await
            .unwrap();
        assert_eq!(resp.status(), actix_web::http::StatusCode::OK);

        let body: BulkActionResponse = resp.json().await.unwrap();
        assert_eq!(body.succeeded, 1);
        assert_eq!(body.failed, 1);
        assert_eq!(body.errors.len(), 1);
        assert_eq!(body.errors[0].id, bad_id.to_string());
    }

    #[actix_rt::test]
    async fn test_bulk_trash_empty_list() {
        let Some((srv, _meta, _s3)) = build_test_app().await else {
            eprintln!("Skipping test_bulk_trash_empty_list: env not available");
            return;
        };
        let payload = serde_json::json!({ "file_ids": [] });
        let mut resp = srv
            .post("/api/v1/files/bulk/trash")
            .send_json(&payload)
            .await
            .unwrap();
        assert_eq!(resp.status(), actix_web::http::StatusCode::OK);

        let body: BulkActionResponse = resp.json().await.unwrap();
        assert_eq!(body.succeeded, 0);
        assert_eq!(body.failed, 0);
    }

    #[actix_rt::test]
    async fn test_bulk_move_happy_path() {
        let Some((srv, meta, s3)) = build_test_app().await else {
            eprintln!("Skipping test_bulk_move_happy_path: env not available");
            return;
        };
        let f1 = seed_file(&meta, &s3).await;
        let f2 = seed_file(&meta, &s3).await;
        let target = Uuid::new_v4();

        let payload = serde_json::json!({
            "file_ids": [f1.id.to_string(), f2.id.to_string()],
            "target_folder_id": target.to_string()
        });
        let mut resp = srv
            .post("/api/v1/files/bulk/move")
            .send_json(&payload)
            .await
            .unwrap();
        assert_eq!(resp.status(), actix_web::http::StatusCode::OK);

        let body: BulkActionResponse = resp.json().await.unwrap();
        assert_eq!(body.succeeded, 2);
        assert_eq!(body.failed, 0);

        let moved1 = meta.get_file(&f1.id).await.unwrap();
        assert_eq!(moved1.folder_id, Some(target));
    }

    #[actix_rt::test]
    async fn test_bulk_move_partial_failure() {
        let Some((srv, meta, s3)) = build_test_app().await else {
            eprintln!("Skipping test_bulk_move_partial_failure: env not available");
            return;
        };
        let f1 = seed_file(&meta, &s3).await;
        let bad_id = Uuid::new_v4();
        let target = Uuid::new_v4();

        let payload = serde_json::json!({
            "file_ids": [f1.id.to_string(), bad_id.to_string()],
            "target_folder_id": target.to_string()
        });
        let mut resp = srv
            .post("/api/v1/files/bulk/move")
            .send_json(&payload)
            .await
            .unwrap();
        assert_eq!(resp.status(), actix_web::http::StatusCode::OK);

        let body: BulkActionResponse = resp.json().await.unwrap();
        assert_eq!(body.succeeded, 1);
        assert_eq!(body.failed, 1);
    }

    #[actix_rt::test]
    async fn test_bulk_move_empty_list() {
        let Some((srv, _meta, _s3)) = build_test_app().await else {
            eprintln!("Skipping test_bulk_move_empty_list: env not available");
            return;
        };
        let payload = serde_json::json!({
            "file_ids": [],
            "target_folder_id": null
        });
        let mut resp = srv
            .post("/api/v1/files/bulk/move")
            .send_json(&payload)
            .await
            .unwrap();
        assert_eq!(resp.status(), actix_web::http::StatusCode::OK);

        let body: BulkActionResponse = resp.json().await.unwrap();
        assert_eq!(body.succeeded, 0);
        assert_eq!(body.failed, 0);
    }

    #[actix_rt::test]
    async fn test_bulk_download_happy_path() {
        let Some((srv, meta, s3)) = build_test_app().await else {
            eprintln!("Skipping test_bulk_download_happy_path: env not available");
            return;
        };
        let f1 = seed_file(&meta, &s3).await;
        let f2 = seed_file(&meta, &s3).await;

        let payload = serde_json::json!({
            "file_ids": [f1.id.to_string(), f2.id.to_string()]
        });
        let mut resp = srv
            .post("/api/v1/files/bulk/download")
            .send_json(&payload)
            .await
            .unwrap();
        assert_eq!(resp.status(), actix_web::http::StatusCode::OK);

        let body: BulkDownloadResponse = resp.json().await.unwrap();
        assert_eq!(body.urls.len(), 2);
        assert!(!body.urls[0].url.is_empty());
        assert!(!body.urls[1].url.is_empty());
        assert_eq!(body.urls[0].expires_in_secs, 3600);
    }

    #[actix_rt::test]
    async fn test_bulk_download_empty_list() {
        let Some((srv, _meta, _s3)) = build_test_app().await else {
            eprintln!("Skipping test_bulk_download_empty_list: env not available");
            return;
        };
        let payload = serde_json::json!({ "file_ids": [] });
        let mut resp = srv
            .post("/api/v1/files/bulk/download")
            .send_json(&payload)
            .await
            .unwrap();
        assert_eq!(resp.status(), actix_web::http::StatusCode::OK);

        let body: BulkDownloadResponse = resp.json().await.unwrap();
        assert!(body.urls.is_empty());
    }
}
