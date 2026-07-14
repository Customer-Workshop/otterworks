use actix_web::{HttpResponse, ResponseError};

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
        let (status, code) = match self {
            ServiceError::FileNotFound(_)
            | ServiceError::FolderNotFound(_)
            | ServiceError::VersionNotFound(_)
            | ServiceError::ShareNotFound(_) => {
                (actix_web::http::StatusCode::NOT_FOUND, "NOT_FOUND")
            }
            ServiceError::BadRequest(_) => {
                (actix_web::http::StatusCode::BAD_REQUEST, "BAD_REQUEST")
            }
            ServiceError::FileTooLarge { .. } => (
                actix_web::http::StatusCode::PAYLOAD_TOO_LARGE,
                "PAYLOAD_TOO_LARGE",
            ),
            ServiceError::Unauthorized(_) => {
                (actix_web::http::StatusCode::UNAUTHORIZED, "UNAUTHORIZED")
            }
            ServiceError::Forbidden(_) => (actix_web::http::StatusCode::FORBIDDEN, "FORBIDDEN"),
            ServiceError::S3Error(_)
            | ServiceError::DynamoError(_)
            | ServiceError::SnsError(_)
            | ServiceError::Internal(_) => (
                actix_web::http::StatusCode::INTERNAL_SERVER_ERROR,
                "INTERNAL_ERROR",
            ),
        };

        HttpResponse::build(status).json(ErrorResponse {
            error: ErrorDetail {
                code: code.to_string(),
                message: self.to_string(),
                status: status.as_u16(),
            },
        })
    }
}

#[derive(Debug, serde::Serialize)]
pub struct ErrorResponse {
    pub error: ErrorDetail,
}

#[derive(Debug, serde::Serialize)]
pub struct ErrorDetail {
    pub code: String,
    pub message: String,
    pub status: u16,
}

pub async fn route_not_found() -> HttpResponse {
    HttpResponse::NotFound().json(ErrorResponse {
        error: ErrorDetail {
            code: "NOT_FOUND".to_string(),
            message: "Route not found".to_string(),
            status: 404,
        },
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use actix_web::body::to_bytes;
    use serde_json::json;

    #[actix_rt::test]
    async fn serializes_standard_error_response() {
        let response = ServiceError::FileNotFound("file-123".into()).error_response();
        let status = response.status();
        let body = to_bytes(response.into_body()).await.unwrap();

        assert_eq!(status, actix_web::http::StatusCode::NOT_FOUND);
        assert_eq!(
            serde_json::from_slice::<serde_json::Value>(&body).unwrap(),
            json!({
                "error": {
                    "code": "NOT_FOUND",
                    "message": "File not found: file-123",
                    "status": 404
                }
            })
        );
    }
}
