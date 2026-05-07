use actix_multipart::Multipart;
use actix_web::{web, HttpRequest, HttpResponse};
use bytes::BytesMut;
use chrono::Utc;
use futures_util::StreamExt;
use uuid::Uuid;

use crate::config::AppConfig;
use crate::errors::ServiceError;
use crate::events::EventPublisher;
use crate::metadata::MetadataClient;
use crate::middleware;
use crate::models::{
    CreateFolderRequest, DownloadResponse, FileMetadata, FileShare, FileVersion, Folder,
    HealthResponse, ListFilesQuery, ListFilesResponse, ListVersionsResponse, MoveFileRequest,
    ShareFileRequest, ShareFileResponse, UpdateFolderRequest, UploadResponse,
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

fn extract_user_id(req: &HttpRequest) -> Result<Uuid, ServiceError> {
    let header = req
        .headers()
        .get("x-user-id")
        .and_then(|v| v.to_str().ok())
        .ok_or_else(|| ServiceError::Unauthorized("missing X-User-ID header".into()))?;
    header
        .parse::<Uuid>()
        .map_err(|e| ServiceError::Unauthorized(format!("invalid X-User-ID: {e}")))
}

// -- File Handlers --

pub async fn upload_file(
    req: HttpRequest,
    s3: web::Data<S3Client>,
    meta: web::Data<MetadataClient>,
    events: web::Data<EventPublisher>,
    config: web::Data<AppConfig>,
    mut payload: Multipart,
) -> Result<HttpResponse, ServiceError> {
    let mut file_bytes = BytesMut::new();
    let mut file_name = String::from("unnamed");
    let mut content_type = String::from("application/octet-stream");
    let mut _owner_id: Option<Uuid> = None;
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
                _owner_id = Some(
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

    let owner = extract_user_id(&req)?;

    if file_bytes.is_empty() {
        return Err(ServiceError::BadRequest("file field is required".into()));
    }

    let file_id = Uuid::new_v4();
    let s3_key = format!("files/{}/{}", owner, file_id);
    let now = Utc::now();
    let size = file_bytes.len() as u64;

    s3.upload_object(&s3_key, file_bytes.freeze(), &content_type)
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
        .file_uploaded(&file_id, &owner, folder_id.as_ref())
        .await;

    tracing::info!(file_id = %file_id, name = %file_meta.name, size = %size, "File uploaded");

    Ok(HttpResponse::Created().json(UploadResponse { file: file_meta }))
}

pub async fn get_file_metadata(
    req: HttpRequest,
    meta: web::Data<MetadataClient>,
    path: web::Path<String>,
) -> Result<HttpResponse, ServiceError> {
    let user_id = extract_user_id(&req)?;
    let file_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid file id: {e}")))?;
    let file = meta.get_file(&file_id).await?;
    if file.owner_id != user_id {
        return Err(ServiceError::Forbidden("you do not own this file".into()));
    }
    Ok(HttpResponse::Ok().json(file))
}

pub async fn list_files(
    req: HttpRequest,
    meta: web::Data<MetadataClient>,
    query: web::Query<ListFilesQuery>,
) -> Result<HttpResponse, ServiceError> {
    let user_id = extract_user_id(&req)?;
    let include_trashed = query.include_trashed.unwrap_or(false);
    let files = meta
        .list_files(query.folder_id, Some(user_id), include_trashed)
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

pub async fn delete_file(
    req: HttpRequest,
    s3: web::Data<S3Client>,
    meta: web::Data<MetadataClient>,
    events: web::Data<EventPublisher>,
    path: web::Path<String>,
) -> Result<HttpResponse, ServiceError> {
    let user_id = extract_user_id(&req)?;
    let file_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid file id: {e}")))?;

    let file = meta.get_file(&file_id).await?;
    if file.owner_id != user_id {
        return Err(ServiceError::Forbidden("you do not own this file".into()));
    }
    meta.delete_file(&file_id).await?;
    s3.delete_object(&file.s3_key).await?;

    let _ = events.file_deleted(&file_id, &file.owner_id).await;

    tracing::info!(file_id = %file_id, "File deleted");
    Ok(HttpResponse::NoContent().finish())
}

pub async fn download_file(
    req: HttpRequest,
    s3: web::Data<S3Client>,
    meta: web::Data<MetadataClient>,
    path: web::Path<String>,
) -> Result<HttpResponse, ServiceError> {
    let user_id = extract_user_id(&req)?;
    let file_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid file id: {e}")))?;

    let file = meta.get_file(&file_id).await?;
    if file.owner_id != user_id {
        return Err(ServiceError::Forbidden("you do not own this file".into()));
    }
    let url = s3.presigned_download_url(&file.s3_key, 3600).await?;

    Ok(HttpResponse::Ok().json(DownloadResponse {
        url,
        expires_in_secs: 3600,
    }))
}

pub async fn move_file(
    req: HttpRequest,
    meta: web::Data<MetadataClient>,
    events: web::Data<EventPublisher>,
    path: web::Path<String>,
    body: web::Json<MoveFileRequest>,
) -> Result<HttpResponse, ServiceError> {
    let user_id = extract_user_id(&req)?;
    let file_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid file id: {e}")))?;

    let existing = meta.get_file(&file_id).await?;
    if existing.owner_id != user_id {
        return Err(ServiceError::Forbidden("you do not own this file".into()));
    }

    let file = meta.move_file(&file_id, body.folder_id).await?;

    let _ = events
        .file_moved(&file_id, &file.owner_id, body.folder_id.as_ref())
        .await;

    tracing::info!(file_id = %file_id, folder_id = ?body.folder_id, "File moved");
    Ok(HttpResponse::Ok().json(file))
}

pub async fn list_versions(
    req: HttpRequest,
    meta: web::Data<MetadataClient>,
    path: web::Path<String>,
) -> Result<HttpResponse, ServiceError> {
    let user_id = extract_user_id(&req)?;
    let file_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid file id: {e}")))?;

    let file = meta.get_file(&file_id).await?;
    if file.owner_id != user_id {
        return Err(ServiceError::Forbidden("you do not own this file".into()));
    }

    let versions = meta.list_versions(&file_id).await?;
    Ok(HttpResponse::Ok().json(ListVersionsResponse { versions }))
}

pub async fn trash_file(
    req: HttpRequest,
    meta: web::Data<MetadataClient>,
    path: web::Path<String>,
) -> Result<HttpResponse, ServiceError> {
    let user_id = extract_user_id(&req)?;
    let file_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid file id: {e}")))?;

    let existing = meta.get_file(&file_id).await?;
    if existing.owner_id != user_id {
        return Err(ServiceError::Forbidden("you do not own this file".into()));
    }

    let file = meta.trash_file(&file_id).await?;
    tracing::info!(file_id = %file_id, "File trashed");
    Ok(HttpResponse::Ok().json(file))
}

pub async fn restore_file(
    req: HttpRequest,
    meta: web::Data<MetadataClient>,
    path: web::Path<String>,
) -> Result<HttpResponse, ServiceError> {
    let user_id = extract_user_id(&req)?;
    let file_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid file id: {e}")))?;

    let existing = meta.get_file(&file_id).await?;
    if existing.owner_id != user_id {
        return Err(ServiceError::Forbidden("you do not own this file".into()));
    }

    let file = meta.restore_file(&file_id).await?;
    tracing::info!(file_id = %file_id, "File restored");
    Ok(HttpResponse::Ok().json(file))
}

pub async fn share_file(
    req: HttpRequest,
    meta: web::Data<MetadataClient>,
    events: web::Data<EventPublisher>,
    path: web::Path<String>,
    body: web::Json<ShareFileRequest>,
) -> Result<HttpResponse, ServiceError> {
    let user_id = extract_user_id(&req)?;
    let file_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid file id: {e}")))?;

    let file = meta.get_file(&file_id).await?;
    if file.owner_id != user_id {
        return Err(ServiceError::Forbidden("you do not own this file".into()));
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

// -- Folder Handlers --

pub async fn create_folder(
    req: HttpRequest,
    meta: web::Data<MetadataClient>,
    body: web::Json<CreateFolderRequest>,
) -> Result<HttpResponse, ServiceError> {
    let owner = extract_user_id(&req)?;
    let now = Utc::now();
    let folder = Folder {
        id: Uuid::new_v4(),
        name: body.name.clone(),
        parent_id: body.parent_id,
        owner_id: owner,
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
    req: HttpRequest,
    meta: web::Data<MetadataClient>,
    path: web::Path<String>,
    body: web::Json<UpdateFolderRequest>,
) -> Result<HttpResponse, ServiceError> {
    let user_id = extract_user_id(&req)?;
    let folder_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid folder id: {e}")))?;

    let existing = meta.get_folder(&folder_id).await?;
    if existing.owner_id != user_id {
        return Err(ServiceError::Forbidden("you do not own this folder".into()));
    }

    let folder = meta
        .update_folder(&folder_id, body.name.clone(), body.parent_id)
        .await?;
    Ok(HttpResponse::Ok().json(folder))
}

pub async fn delete_folder(
    req: HttpRequest,
    meta: web::Data<MetadataClient>,
    path: web::Path<String>,
) -> Result<HttpResponse, ServiceError> {
    let user_id = extract_user_id(&req)?;
    let folder_id: Uuid = path
        .into_inner()
        .parse()
        .map_err(|e| ServiceError::BadRequest(format!("invalid folder id: {e}")))?;

    let existing = meta.get_folder(&folder_id).await?;
    if existing.owner_id != user_id {
        return Err(ServiceError::Forbidden("you do not own this folder".into()));
    }

    meta.delete_folder(&folder_id).await?;
    tracing::info!(folder_id = %folder_id, "Folder deleted");
    Ok(HttpResponse::NoContent().finish())
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

    #[actix_rt::test]
    async fn test_extract_user_id_missing_header() {
        let req = actix_web::test::TestRequest::default().to_http_request();
        let result = extract_user_id(&req);
        assert!(result.is_err());
    }

    #[actix_rt::test]
    async fn test_extract_user_id_valid_header() {
        let user_id = Uuid::new_v4();
        let req = actix_web::test::TestRequest::default()
            .insert_header(("x-user-id", user_id.to_string()))
            .to_http_request();
        let result = extract_user_id(&req);
        assert_eq!(result.unwrap(), user_id);
    }

    #[actix_rt::test]
    async fn test_extract_user_id_invalid_uuid() {
        let req = actix_web::test::TestRequest::default()
            .insert_header(("x-user-id", "not-a-uuid"))
            .to_http_request();
        let result = extract_user_id(&req);
        assert!(result.is_err());
    }
}
