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
    use std::env;

    fn clear_env_vars() {
        for key in &[
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
            env::remove_var(key);
        }
    }

    #[test]
    fn server_config_defaults() {
        clear_env_vars();
        let cfg = ServerConfig::from_env();
        assert_eq!(cfg.port, 8082);
        assert_eq!(cfg.max_upload_bytes, 104_857_600);
    }

    #[test]
    fn server_config_custom_port() {
        env::set_var("PORT", "9090");
        let cfg = ServerConfig::from_env();
        assert_eq!(cfg.port, 9090);
        env::remove_var("PORT");
    }

    #[test]
    fn server_config_invalid_port_uses_default() {
        env::set_var("PORT", "not-a-number");
        let cfg = ServerConfig::from_env();
        assert_eq!(cfg.port, 8082);
        env::remove_var("PORT");
    }

    #[test]
    fn server_config_custom_max_upload() {
        env::set_var("MAX_UPLOAD_BYTES", "5242880");
        let cfg = ServerConfig::from_env();
        assert_eq!(cfg.max_upload_bytes, 5_242_880);
        env::remove_var("MAX_UPLOAD_BYTES");
    }

    #[test]
    fn aws_config_defaults() {
        clear_env_vars();
        let cfg = AwsConfig::from_env();
        assert_eq!(cfg.region, "us-east-1");
        assert!(cfg.endpoint_url.is_none());
        assert_eq!(cfg.s3_bucket, "otterworks-files");
        assert_eq!(cfg.dynamodb_table, "otterworks-file-metadata");
        assert_eq!(cfg.dynamodb_folders_table, "otterworks-folders");
        assert_eq!(cfg.dynamodb_versions_table, "otterworks-file-versions");
        assert_eq!(cfg.dynamodb_shares_table, "otterworks-file-shares");
    }

    #[test]
    fn aws_config_custom_endpoint() {
        env::set_var("AWS_ENDPOINT_URL", "http://localhost:4566");
        let cfg = AwsConfig::from_env();
        assert_eq!(
            cfg.endpoint_url,
            Some("http://localhost:4566".to_string())
        );
        env::remove_var("AWS_ENDPOINT_URL");
    }

    #[test]
    fn aws_config_custom_bucket() {
        env::set_var("S3_BUCKET", "my-custom-bucket");
        let cfg = AwsConfig::from_env();
        assert_eq!(cfg.s3_bucket, "my-custom-bucket");
        env::remove_var("S3_BUCKET");
    }

    #[test]
    fn sns_config_default_no_topic() {
        clear_env_vars();
        let cfg = SnsConfig::from_env();
        assert!(cfg.topic_arn.is_none());
    }

    #[test]
    fn sns_config_with_topic_arn() {
        env::set_var("SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:123:my-topic");
        let cfg = SnsConfig::from_env();
        assert_eq!(
            cfg.topic_arn,
            Some("arn:aws:sns:us-east-1:123:my-topic".to_string())
        );
        env::remove_var("SNS_TOPIC_ARN");
    }

    #[test]
    fn app_config_composes_sub_configs() {
        clear_env_vars();
        let cfg = AppConfig::from_env();
        assert_eq!(cfg.server.port, 8082);
        assert_eq!(cfg.aws.region, "us-east-1");
        assert!(cfg.sns.topic_arn.is_none());
    }
}
