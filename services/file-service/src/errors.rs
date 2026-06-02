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

    #[test]
    fn error_display_file_not_found() {
        let err = ServiceError::FileNotFound("abc-123".into());
        assert_eq!(err.to_string(), "File not found: abc-123");
    }

    #[test]
    fn error_display_folder_not_found() {
        let err = ServiceError::FolderNotFound("folder-1".into());
        assert_eq!(err.to_string(), "Folder not found: folder-1");
    }

    #[test]
    fn error_display_version_not_found() {
        let err = ServiceError::VersionNotFound("v3".into());
        assert_eq!(err.to_string(), "Version not found: v3");
    }

    #[test]
    fn error_display_share_not_found() {
        let err = ServiceError::ShareNotFound("share-1".into());
        assert_eq!(err.to_string(), "Share not found: share-1");
    }

    #[test]
    fn error_display_bad_request() {
        let err = ServiceError::BadRequest("missing field".into());
        assert_eq!(err.to_string(), "Bad request: missing field");
    }

    #[test]
    fn error_display_file_too_large() {
        let err = ServiceError::FileTooLarge {
            max_bytes: 100,
            actual_bytes: 200,
        };
        assert_eq!(
            err.to_string(),
            "File too large: max 100 bytes, got 200 bytes"
        );
    }

    #[test]
    fn error_display_unauthorized() {
        let err = ServiceError::Unauthorized("no token".into());
        assert_eq!(err.to_string(), "Unauthorized: no token");
    }

    #[test]
    fn error_display_forbidden() {
        let err = ServiceError::Forbidden("not owner".into());
        assert_eq!(err.to_string(), "Forbidden: not owner");
    }

    #[test]
    fn error_display_s3_error() {
        let err = ServiceError::S3Error("connection refused".into());
        assert_eq!(err.to_string(), "S3 error: connection refused");
    }

    #[test]
    fn error_display_dynamo_error() {
        let err = ServiceError::DynamoError("table not found".into());
        assert_eq!(err.to_string(), "DynamoDB error: table not found");
    }

    #[test]
    fn error_display_sns_error() {
        let err = ServiceError::SnsError("publish failed".into());
        assert_eq!(err.to_string(), "SNS error: publish failed");
    }

    #[test]
    fn error_display_internal() {
        let err = ServiceError::Internal("unexpected".into());
        assert_eq!(err.to_string(), "Internal error: unexpected");
    }

    #[test]
    fn error_response_status_codes() {
        let cases: Vec<(ServiceError, StatusCode, &str)> = vec![
            (
                ServiceError::FileNotFound("x".into()),
                StatusCode::NOT_FOUND,
                "file_not_found",
            ),
            (
                ServiceError::FolderNotFound("x".into()),
                StatusCode::NOT_FOUND,
                "folder_not_found",
            ),
            (
                ServiceError::VersionNotFound("x".into()),
                StatusCode::NOT_FOUND,
                "version_not_found",
            ),
            (
                ServiceError::ShareNotFound("x".into()),
                StatusCode::NOT_FOUND,
                "share_not_found",
            ),
            (
                ServiceError::BadRequest("x".into()),
                StatusCode::BAD_REQUEST,
                "bad_request",
            ),
            (
                ServiceError::FileTooLarge {
                    max_bytes: 1,
                    actual_bytes: 2,
                },
                StatusCode::PAYLOAD_TOO_LARGE,
                "file_too_large",
            ),
            (
                ServiceError::Unauthorized("x".into()),
                StatusCode::UNAUTHORIZED,
                "unauthorized",
            ),
            (
                ServiceError::Forbidden("x".into()),
                StatusCode::FORBIDDEN,
                "forbidden",
            ),
            (
                ServiceError::S3Error("x".into()),
                StatusCode::INTERNAL_SERVER_ERROR,
                "storage_error",
            ),
            (
                ServiceError::DynamoError("x".into()),
                StatusCode::INTERNAL_SERVER_ERROR,
                "metadata_error",
            ),
            (
                ServiceError::SnsError("x".into()),
                StatusCode::INTERNAL_SERVER_ERROR,
                "event_error",
            ),
            (
                ServiceError::Internal("x".into()),
                StatusCode::INTERNAL_SERVER_ERROR,
                "internal_error",
            ),
        ];

        for (err, expected_status, expected_type) in cases {
            let resp = err.error_response();
            assert_eq!(
                resp.status(),
                expected_status,
                "Wrong status for error type: {}",
                expected_type
            );
        }
    }

    #[actix_rt::test]
    async fn error_response_body_is_json() {
        let err = ServiceError::FileNotFound("file-abc".into());
        let resp = err.error_response();
        let body = to_bytes(resp.into_body()).await.unwrap();
        let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["error"], "file_not_found");
        assert!(json["message"].as_str().unwrap().contains("file-abc"));
    }

    #[test]
    fn error_response_display() {
        let resp = ErrorResponse {
            error: "test_error".into(),
            message: "something went wrong".into(),
        };
        assert_eq!(resp.to_string(), "test_error: something went wrong");
    }
}
