use file_service::config::{AppConfig, AwsConfig, ServerConfig, SnsConfig};

#[test]
fn server_config_defaults() {
    // Clear env vars that might override defaults
    std::env::remove_var("PORT");
    std::env::remove_var("MAX_UPLOAD_BYTES");

    let cfg = ServerConfig::from_env();
    assert_eq!(cfg.port, 8082);
    assert_eq!(cfg.max_upload_bytes, 104_857_600); // 100 MB
}

#[test]
fn server_config_from_env() {
    std::env::set_var("PORT", "9999");
    std::env::set_var("MAX_UPLOAD_BYTES", "50000");

    let cfg = ServerConfig::from_env();
    assert_eq!(cfg.port, 9999);
    assert_eq!(cfg.max_upload_bytes, 50000);

    // Clean up
    std::env::remove_var("PORT");
    std::env::remove_var("MAX_UPLOAD_BYTES");
}

#[test]
fn server_config_invalid_port_uses_default() {
    std::env::set_var("PORT", "not-a-number");
    let cfg = ServerConfig::from_env();
    assert_eq!(cfg.port, 8082);
    std::env::remove_var("PORT");
}

#[test]
fn aws_config_defaults() {
    std::env::remove_var("AWS_REGION");
    std::env::remove_var("AWS_ENDPOINT_URL");
    std::env::remove_var("S3_BUCKET");
    std::env::remove_var("DYNAMODB_TABLE");
    std::env::remove_var("DYNAMODB_FOLDERS_TABLE");
    std::env::remove_var("DYNAMODB_VERSIONS_TABLE");
    std::env::remove_var("DYNAMODB_SHARES_TABLE");

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
    std::env::set_var("AWS_ENDPOINT_URL", "http://localhost:4566");
    let cfg = AwsConfig::from_env();
    assert_eq!(cfg.endpoint_url, Some("http://localhost:4566".into()));
    std::env::remove_var("AWS_ENDPOINT_URL");
}

#[test]
fn sns_config_defaults() {
    std::env::remove_var("SNS_TOPIC_ARN");
    let cfg = SnsConfig::from_env();
    assert!(cfg.topic_arn.is_none());
}

#[test]
fn sns_config_with_arn() {
    std::env::set_var("SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:123456:my-topic");
    let cfg = SnsConfig::from_env();
    assert_eq!(
        cfg.topic_arn,
        Some("arn:aws:sns:us-east-1:123456:my-topic".into())
    );
    std::env::remove_var("SNS_TOPIC_ARN");
}

#[test]
fn app_config_from_env_builds_all_sections() {
    // Just verify it doesn't panic
    std::env::remove_var("PORT");
    std::env::remove_var("AWS_ENDPOINT_URL");
    std::env::remove_var("SNS_TOPIC_ARN");
    let cfg = AppConfig::from_env();
    assert_eq!(cfg.server.port, 8082);
    assert!(cfg.sns.topic_arn.is_none());
}
