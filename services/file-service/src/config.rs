use std::env;

#[derive(Clone, Debug)]
pub struct AppConfig {
    pub server: ServerConfig,
    pub aws: AwsConfig,
    pub sns: SnsConfig,
}

#[derive(Clone, Debug)]
pub struct ServerConfig {
    pub port: u16,
    pub max_upload_bytes: u64,
}

#[derive(Clone, Debug)]
pub struct AwsConfig {
    pub region: String,
    pub endpoint_url: Option<String>,
    pub s3_bucket: String,
    pub dynamodb_table: String,
    pub dynamodb_folders_table: String,
    pub dynamodb_versions_table: String,
    pub dynamodb_shares_table: String,
}

#[derive(Clone, Debug)]
pub struct SnsConfig {
    pub topic_arn: Option<String>,
}

impl AppConfig {
    pub fn from_env() -> Self {
        Self {
            server: ServerConfig::from_env(),
            aws: AwsConfig::from_env(),
            sns: SnsConfig::from_env(),
        }
    }
}

impl ServerConfig {
    pub fn from_env() -> Self {
        Self {
            port: env::var("PORT")
                .unwrap_or_else(|_| "8082".into())
                .parse()
                .unwrap_or(8082),
            max_upload_bytes: env::var("MAX_UPLOAD_BYTES")
                .unwrap_or_else(|_| "104857600".into()) // 100 MB
                .parse()
                .unwrap_or(104_857_600),
        }
    }
}

impl AwsConfig {
    pub fn from_env() -> Self {
        Self {
            region: env::var("AWS_REGION").unwrap_or_else(|_| "us-east-1".into()),
            endpoint_url: env::var("AWS_ENDPOINT_URL").ok(),
            s3_bucket: env::var("S3_BUCKET").unwrap_or_else(|_| "otterworks-files".into()),
            dynamodb_table: env::var("DYNAMODB_TABLE")
                .unwrap_or_else(|_| "otterworks-file-metadata".into()),
            dynamodb_folders_table: env::var("DYNAMODB_FOLDERS_TABLE")
                .unwrap_or_else(|_| "otterworks-folders".into()),
            dynamodb_versions_table: env::var("DYNAMODB_VERSIONS_TABLE")
                .unwrap_or_else(|_| "otterworks-file-versions".into()),
            dynamodb_shares_table: env::var("DYNAMODB_SHARES_TABLE")
                .unwrap_or_else(|_| "otterworks-file-shares".into()),
        }
    }
}

impl SnsConfig {
    pub fn from_env() -> Self {
        Self {
            topic_arn: env::var("SNS_TOPIC_ARN").ok(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Mutex, OnceLock};

    fn env_lock() -> std::sync::MutexGuard<'static, ()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| Mutex::new(())).lock().unwrap()
    }

    #[test]
    fn uses_defaults_when_environment_is_missing() {
        let _lock = env_lock();
        for key in [
            "PORT",
            "MAX_UPLOAD_BYTES",
            "AWS_REGION",
            "AWS_ENDPOINT_URL",
            "S3_BUCKET",
            "DYNAMODB_TABLE",
            "DYNAMODB_FOLDERS_TABLE",
            "DYNAMODB_VERSIONS_TABLE",
            "DYNAMODB_SHARES_TABLE",
            "SNS_TOPIC_ARN",
        ] {
            std::env::remove_var(key);
        }

        let config = AppConfig::from_env();
        assert_eq!(config.server.port, 8082);
        assert_eq!(config.server.max_upload_bytes, 104_857_600);
        assert_eq!(config.aws.region, "us-east-1");
        assert_eq!(config.aws.s3_bucket, "otterworks-files");
        assert_eq!(config.sns.topic_arn, None);
    }

    #[test]
    fn parses_configured_values() {
        let _lock = env_lock();
        std::env::set_var("PORT", "9000");
        std::env::set_var("MAX_UPLOAD_BYTES", "2048");
        std::env::set_var("AWS_ENDPOINT_URL", "http://localhost:4566");
        std::env::set_var("SNS_TOPIC_ARN", "arn:test");

        let config = AppConfig::from_env();
        assert_eq!(config.server.port, 9000);
        assert_eq!(config.server.max_upload_bytes, 2048);
        assert_eq!(
            config.aws.endpoint_url.as_deref(),
            Some("http://localhost:4566")
        );
        assert_eq!(config.sns.topic_arn.as_deref(), Some("arn:test"));

        for key in [
            "PORT",
            "MAX_UPLOAD_BYTES",
            "AWS_ENDPOINT_URL",
            "SNS_TOPIC_ARN",
        ] {
            std::env::remove_var(key);
        }
    }
}
