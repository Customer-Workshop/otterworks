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

    fn all_variants() -> Vec<(ServiceError, StatusCode, &'static str)> {
        vec![
            (
                ServiceError::FileNotFound("f1".into()),
                StatusCode::NOT_FOUND,
                "file_not_found",
            ),
            (
                ServiceError::FolderNotFound("d1".into()),
                StatusCode::NOT_FOUND,
                "folder_not_found",
            ),
            (
                ServiceError::VersionNotFound("v1".into()),
                StatusCode::NOT_FOUND,
                "version_not_found",
            ),
            (
                ServiceError::ShareNotFound("s1".into()),
                StatusCode::NOT_FOUND,
                "share_not_found",
            ),
            (
                ServiceError::BadRequest("invalid".into()),
                StatusCode::BAD_REQUEST,
                "bad_request",
            ),
            (
                ServiceError::FileTooLarge {
                    max_bytes: 100,
                    actual_bytes: 200,
                },
                StatusCode::PAYLOAD_TOO_LARGE,
                "file_too_large",
            ),
            (
                ServiceError::Unauthorized("no token".into()),
                StatusCode::UNAUTHORIZED,
                "unauthorized",
            ),
            (
                ServiceError::Forbidden("denied".into()),
                StatusCode::FORBIDDEN,
                "forbidden",
            ),
            (
                ServiceError::S3Error("s3 fail".into()),
                StatusCode::INTERNAL_SERVER_ERROR,
                "storage_error",
            ),
            (
                ServiceError::DynamoError("dynamo fail".into()),
                StatusCode::INTERNAL_SERVER_ERROR,
                "metadata_error",
            ),
            (
                ServiceError::SnsError("sns fail".into()),
                StatusCode::INTERNAL_SERVER_ERROR,
                "event_error",
            ),
            (
                ServiceError::Internal("unexpected".into()),
                StatusCode::INTERNAL_SERVER_ERROR,
                "internal_error",
            ),
        ]
    }

    #[test]
    fn test_status_codes() {
        for (error, expected_status, _) in all_variants() {
            let resp = error.error_response();
            assert_eq!(
                resp.status(),
                expected_status,
                "Wrong status for {:?}",
                error
            );
        }
    }

    #[actix_rt::test]
    async fn test_response_body_error_types() {
        for (error, _, expected_type) in all_variants() {
            let resp = error.error_response();
            let body = to_bytes(resp.into_body()).await.unwrap();
            let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
            assert_eq!(
                json["error"].as_str().unwrap(),
                expected_type,
                "Wrong error type for {:?}",
                error
            );
            assert!(
                json["message"].as_str().is_some(),
                "Missing message for {:?}",
                error
            );
        }
    }

    #[test]
    fn test_display_file_not_found() {
        let e = ServiceError::FileNotFound("abc".into());
        assert_eq!(e.to_string(), "File not found: abc");
    }

    #[test]
    fn test_display_folder_not_found() {
        let e = ServiceError::FolderNotFound("xyz".into());
        assert_eq!(e.to_string(), "Folder not found: xyz");
    }

    #[test]
    fn test_display_version_not_found() {
        let e = ServiceError::VersionNotFound("v2".into());
        assert_eq!(e.to_string(), "Version not found: v2");
    }

    #[test]
    fn test_display_share_not_found() {
        let e = ServiceError::ShareNotFound("s3".into());
        assert_eq!(e.to_string(), "Share not found: s3");
    }

    #[test]
    fn test_display_bad_request() {
        let e = ServiceError::BadRequest("missing field".into());
        assert_eq!(e.to_string(), "Bad request: missing field");
    }

    #[test]
    fn test_display_file_too_large() {
        let e = ServiceError::FileTooLarge {
            max_bytes: 100,
            actual_bytes: 200,
        };
        assert_eq!(
            e.to_string(),
            "File too large: max 100 bytes, got 200 bytes"
        );
    }

    #[test]
    fn test_display_unauthorized() {
        let e = ServiceError::Unauthorized("no creds".into());
        assert_eq!(e.to_string(), "Unauthorized: no creds");
    }

    #[test]
    fn test_display_forbidden() {
        let e = ServiceError::Forbidden("nope".into());
        assert_eq!(e.to_string(), "Forbidden: nope");
    }

    #[test]
    fn test_display_s3_error() {
        let e = ServiceError::S3Error("timeout".into());
        assert_eq!(e.to_string(), "S3 error: timeout");
    }

    #[test]
    fn test_display_dynamo_error() {
        let e = ServiceError::DynamoError("throttle".into());
        assert_eq!(e.to_string(), "DynamoDB error: throttle");
    }

    #[test]
    fn test_display_sns_error() {
        let e = ServiceError::SnsError("publish fail".into());
        assert_eq!(e.to_string(), "SNS error: publish fail");
    }

    #[test]
    fn test_display_internal() {
        let e = ServiceError::Internal("oops".into());
        assert_eq!(e.to_string(), "Internal error: oops");
    }

    #[test]
    fn test_error_response_serialization() {
        let resp = ErrorResponse {
            error: "file_not_found".into(),
            message: "File not found: abc".into(),
        };
        let json = serde_json::to_string(&resp).unwrap();
        let parsed: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed["error"], "file_not_found");
        assert_eq!(parsed["message"], "File not found: abc");
    }

    #[test]
    fn test_error_response_display() {
        let resp = ErrorResponse {
            error: "bad_request".into(),
            message: "missing name".into(),
        };
        assert_eq!(resp.to_string(), "bad_request: missing name");
    }
}
