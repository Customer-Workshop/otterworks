use actix_web::{HttpResponse, ResponseError};
use std::fmt;

#[derive(Debug, thiserror::Error)]
pub enum ServiceError {
    #[error("File not found: {0}")]
    FileNotFound(String),

    #[error("Folder not found: {0}")]
    FolderNotFound(String),

    #[error("Version not found: {0}")]
    VersionNotFound(String),

    #[error("Share not found: {0}")]
    ShareNotFound(String),

    #[error("Bad request: {0}")]
    BadRequest(String),

    #[error("File too large: max {max_bytes} bytes, got {actual_bytes} bytes")]
    FileTooLarge { max_bytes: u64, actual_bytes: u64 },

    #[error("Unauthorized: {0}")]
    Unauthorized(String),

    #[error("Forbidden: {0}")]
    Forbidden(String),

    #[error("S3 error: {0}")]
    S3Error(String),

    #[error("DynamoDB error: {0}")]
    DynamoError(String),

    #[error("SNS error: {0}")]
    SnsError(String),

    #[error("Internal error: {0}")]
    Internal(String),
}

impl ResponseError for ServiceError {
    fn error_response(&self) -> HttpResponse {
        let (status, error_type) = match self {
            ServiceError::FileNotFound(_) => {
                (actix_web::http::StatusCode::NOT_FOUND, "file_not_found")
            }
            ServiceError::FolderNotFound(_) => {
                (actix_web::http::StatusCode::NOT_FOUND, "folder_not_found")
            }
            ServiceError::VersionNotFound(_) => {
                (actix_web::http::StatusCode::NOT_FOUND, "version_not_found")
            }
            ServiceError::ShareNotFound(_) => {
                (actix_web::http::StatusCode::NOT_FOUND, "share_not_found")
            }
            ServiceError::BadRequest(_) => {
                (actix_web::http::StatusCode::BAD_REQUEST, "bad_request")
            }
            ServiceError::FileTooLarge { .. } => (
                actix_web::http::StatusCode::PAYLOAD_TOO_LARGE,
                "file_too_large",
            ),
            ServiceError::Unauthorized(_) => {
                (actix_web::http::StatusCode::UNAUTHORIZED, "unauthorized")
            }
            ServiceError::Forbidden(_) => (actix_web::http::StatusCode::FORBIDDEN, "forbidden"),
            ServiceError::S3Error(_) => (
                actix_web::http::StatusCode::INTERNAL_SERVER_ERROR,
                "storage_error",
            ),
            ServiceError::DynamoError(_) => (
                actix_web::http::StatusCode::INTERNAL_SERVER_ERROR,
                "metadata_error",
            ),
            ServiceError::SnsError(_) => (
                actix_web::http::StatusCode::INTERNAL_SERVER_ERROR,
                "event_error",
            ),
            ServiceError::Internal(_) => (
                actix_web::http::StatusCode::INTERNAL_SERVER_ERROR,
                "internal_error",
            ),
        };

        HttpResponse::build(status).json(ErrorResponse {
            error: error_type.to_string(),
            message: self.to_string(),
        })
    }
}

#[derive(Debug, serde::Serialize)]
pub struct ErrorResponse {
    pub error: String,
    pub message: String,
}

impl fmt::Display for ErrorResponse {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.error, self.message)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use actix_web::body::to_bytes;
    use actix_web::http::StatusCode;

    async fn response_parts(err: ServiceError) -> (StatusCode, serde_json::Value) {
        let resp = err.error_response();
        let status = resp.status();
        let body = to_bytes(resp.into_body()).await.unwrap();
        (status, serde_json::from_slice(&body).unwrap())
    }

    #[actix_web::test]
    async fn not_found_variants_map_to_404() {
        for (err, expected_type) in [
            (ServiceError::FileNotFound("f".into()), "file_not_found"),
            (ServiceError::FolderNotFound("d".into()), "folder_not_found"),
            (
                ServiceError::VersionNotFound("v".into()),
                "version_not_found",
            ),
            (ServiceError::ShareNotFound("s".into()), "share_not_found"),
        ] {
            let (status, body) = response_parts(err).await;
            assert_eq!(status, StatusCode::NOT_FOUND);
            assert_eq!(body["error"], expected_type);
        }
    }

    #[actix_web::test]
    async fn client_errors_map_to_4xx() {
        let (status, body) = response_parts(ServiceError::BadRequest("bad".into())).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(body["error"], "bad_request");

        let (status, body) = response_parts(ServiceError::Unauthorized("no".into())).await;
        assert_eq!(status, StatusCode::UNAUTHORIZED);
        assert_eq!(body["error"], "unauthorized");

        let (status, body) = response_parts(ServiceError::Forbidden("no".into())).await;
        assert_eq!(status, StatusCode::FORBIDDEN);
        assert_eq!(body["error"], "forbidden");
    }

    #[actix_web::test]
    async fn file_too_large_maps_to_413_with_sizes_in_message() {
        let (status, body) = response_parts(ServiceError::FileTooLarge {
            max_bytes: 100,
            actual_bytes: 200,
        })
        .await;
        assert_eq!(status, StatusCode::PAYLOAD_TOO_LARGE);
        assert_eq!(body["error"], "file_too_large");
        let message = body["message"].as_str().unwrap();
        assert!(message.contains("100"));
        assert!(message.contains("200"));
    }

    #[actix_web::test]
    async fn backend_errors_map_to_500_without_leaking_variant_names() {
        for (err, expected_type) in [
            (ServiceError::S3Error("s3".into()), "storage_error"),
            (ServiceError::DynamoError("ddb".into()), "metadata_error"),
            (ServiceError::SnsError("sns".into()), "event_error"),
            (ServiceError::Internal("boom".into()), "internal_error"),
        ] {
            let (status, body) = response_parts(err).await;
            assert_eq!(status, StatusCode::INTERNAL_SERVER_ERROR);
            assert_eq!(body["error"], expected_type);
        }
    }
}
