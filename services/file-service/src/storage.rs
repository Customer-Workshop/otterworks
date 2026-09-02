use aws_sdk_s3::presigning::PresigningConfig;
use bytes::Bytes;
use std::time::Duration;

use crate::config::AwsConfig;
use crate::errors::ServiceError;

/// S3 client for file blob operations.
#[derive(Clone)]
pub struct S3Client {
    pub client: aws_sdk_s3::Client,
    pub bucket: String,
}

impl S3Client {
    pub async fn new(config: &AwsConfig) -> Self {
        let mut aws_config_builder = aws_config::defaults(aws_config::BehaviorVersion::latest())
            .region(aws_config::Region::new(config.region.clone()));

        if let Some(endpoint) = &config.endpoint_url {
            aws_config_builder = aws_config_builder.endpoint_url(endpoint);
        }

        let aws_config = aws_config_builder.load().await;
        let s3_config = aws_sdk_s3::config::Builder::from(&aws_config)
            .force_path_style(true)
            .build();
        let client = aws_sdk_s3::Client::from_conf(s3_config);

        Self {
            client,
            bucket: config.s3_bucket.clone(),
        }
    }

    /// Upload file content to S3.
    pub async fn upload_object(
        &self,
        key: &str,
        body: Bytes,
        content_type: &str,
    ) -> Result<(), ServiceError> {
        self.client
            .put_object()
            .bucket(&self.bucket)
            .key(key)
            .body(body.into())
            .content_type(content_type)
            .send()
            .await
            .map_err(|e| ServiceError::S3Error(format!("upload failed: {e}")))?;

        tracing::info!(key = %key, bucket = %self.bucket, "Uploaded object to S3");
        Ok(())
    }

    /// Download file content from S3.
    pub async fn download_object(&self, key: &str) -> Result<Bytes, ServiceError> {
        let resp = self
            .client
            .get_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
            .map_err(|e| ServiceError::S3Error(format!("download failed: {e}")))?;

        let body = resp
            .body
            .collect()
            .await
            .map_err(|e| ServiceError::S3Error(format!("body read failed: {e}")))?;

        Ok(body.into_bytes())
    }

    /// Generate a presigned download URL.
    pub async fn presigned_download_url(
        &self,
        key: &str,
        expires_in_secs: u64,
        response_content_type: Option<&str>,
        response_content_disposition: Option<&str>,
    ) -> Result<String, ServiceError> {
        let presigning = PresigningConfig::expires_in(Duration::from_secs(expires_in_secs))
            .map_err(|e| ServiceError::S3Error(format!("presign config error: {e}")))?;

        let mut request = self.client.get_object().bucket(&self.bucket).key(key);
        if let Some(content_type) = response_content_type {
            request = request.response_content_type(content_type);
        }
        if let Some(content_disposition) = response_content_disposition {
            request = request.response_content_disposition(content_disposition);
        }

        let presigned = request
            .presigned(presigning)
            .await
            .map_err(|e| ServiceError::S3Error(format!("presign failed: {e}")))?;

        Ok(presigned.uri().to_string())
    }

    /// Delete an object from S3.
    pub async fn delete_object(&self, key: &str) -> Result<(), ServiceError> {
        self.client
            .delete_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
            .map_err(|e| ServiceError::S3Error(format!("delete failed: {e}")))?;

        tracing::info!(key = %key, "Deleted object from S3");
        Ok(())
    }

    /// Copy an object within S3 (used for versioning).
    pub async fn copy_object(&self, source_key: &str, dest_key: &str) -> Result<(), ServiceError> {
        let copy_source = format!("{}/{}", self.bucket, source_key);
        self.client
            .copy_object()
            .bucket(&self.bucket)
            .copy_source(&copy_source)
            .key(dest_key)
            .send()
            .await
            .map_err(|e| ServiceError::S3Error(format!("copy failed: {e}")))?;

        tracing::info!(source = %source_key, dest = %dest_key, "Copied object in S3");
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::S3Client;
    use aws_sdk_s3::config::Credentials;

    fn test_client() -> S3Client {
        let config = aws_sdk_s3::Config::builder()
            .region(aws_sdk_s3::config::Region::new("us-east-1"))
            .behavior_version(aws_sdk_s3::config::BehaviorVersion::latest())
            .credentials_provider(Credentials::new(
                "test-access",
                "test-secret",
                None,
                None,
                "test",
            ))
            .endpoint_url("http://localhost:4566")
            .force_path_style(true)
            .build();
        S3Client {
            client: aws_sdk_s3::Client::from_conf(config),
            bucket: "test-bucket".into(),
        }
    }

    #[tokio::test]
    async fn ac_03_presign_includes_response_content_type() {
        let url = test_client()
            .presigned_download_url("files/test", 3600, Some("application/pdf"), None)
            .await
            .expect("presign should succeed");
        assert!(url.contains("response-content-type=application%2Fpdf"));
    }

    #[tokio::test]
    async fn ac_20_presign_omits_response_content_type_when_not_provided() {
        let url = test_client()
            .presigned_download_url("files/test", 3600, None, None)
            .await
            .expect("presign should succeed");
        assert!(!url.contains("response-content-type"));
    }

    #[tokio::test]
    async fn ac_20_attachment_presign_includes_disposition_without_content_type() {
        let url = test_client()
            .presigned_download_url(
                "files/test",
                3600,
                None,
                Some("attachment; filename=\"report.pdf\""),
            )
            .await
            .expect("presign should succeed");
        assert!(url.contains("response-content-disposition"));
        assert!(url.contains("report.pdf"));
        assert!(!url.contains("response-content-type"));
    }
}
