use actix_web::{
    body::BoxBody,
    dev::{Service, ServiceResponse},
    web, App, Error,
};
use aws_sdk_dynamodb::types::{
    AttributeDefinition, BillingMode, KeySchemaElement, KeyType, ScalarAttributeType, TableStatus,
};
use file_service::{
    config::{AppConfig, AwsConfig, ServerConfig, SnsConfig},
    events::EventPublisher,
    metadata::MetadataClient,
    storage::S3Client,
};
use redis::aio::ConnectionManager;
use std::{env, time::Duration};

pub fn aws_endpoint() -> Option<String> {
    env::var("AWS_ENDPOINT_URL").ok()
}

pub fn redis_url() -> Option<String> {
    env::var("REDIS_URL").ok()
}

pub fn test_aws_config(endpoint: &str) -> AwsConfig {
    if env::var_os("AWS_ACCESS_KEY_ID").is_none() {
        env::set_var("AWS_ACCESS_KEY_ID", "test");
    }
    if env::var_os("AWS_SECRET_ACCESS_KEY").is_none() {
        env::set_var("AWS_SECRET_ACCESS_KEY", "test");
    }

    AwsConfig {
        region: "us-east-1".into(),
        endpoint_url: Some(endpoint.into()),
        s3_bucket: "otterworks-files-test".into(),
        dynamodb_table: "otterworks-file-metadata-test".into(),
        dynamodb_folders_table: "otterworks-folders-test".into(),
        dynamodb_versions_table: "otterworks-file-versions-test".into(),
        dynamodb_shares_table: "otterworks-file-shares-test".into(),
    }
}

async fn create_table(
    client: &aws_sdk_dynamodb::Client,
    table_name: &str,
    definitions: Vec<AttributeDefinition>,
    key_schema: Vec<KeySchemaElement>,
) {
    let _ = client
        .create_table()
        .table_name(table_name)
        .set_attribute_definitions(Some(definitions))
        .set_key_schema(Some(key_schema))
        .billing_mode(BillingMode::PayPerRequest)
        .send()
        .await;
}

pub async fn ensure_infra(s3: &S3Client, meta: &MetadataClient) {
    let _ = s3.client.create_bucket().bucket(&s3.bucket).send().await;

    create_table(
        &meta.client,
        &meta.files_table,
        vec![AttributeDefinition::builder()
            .attribute_name("id")
            .attribute_type(ScalarAttributeType::S)
            .build()
            .expect("valid id definition")],
        vec![KeySchemaElement::builder()
            .attribute_name("id")
            .key_type(KeyType::Hash)
            .build()
            .expect("valid id key")],
    )
    .await;
    create_table(
        &meta.client,
        &meta.folders_table,
        vec![AttributeDefinition::builder()
            .attribute_name("id")
            .attribute_type(ScalarAttributeType::S)
            .build()
            .expect("valid id definition")],
        vec![KeySchemaElement::builder()
            .attribute_name("id")
            .key_type(KeyType::Hash)
            .build()
            .expect("valid id key")],
    )
    .await;
    create_table(
        &meta.client,
        &meta.versions_table,
        vec![
            AttributeDefinition::builder()
                .attribute_name("file_id")
                .attribute_type(ScalarAttributeType::S)
                .build()
                .expect("valid file_id definition"),
            AttributeDefinition::builder()
                .attribute_name("version")
                .attribute_type(ScalarAttributeType::N)
                .build()
                .expect("valid version definition"),
        ],
        vec![
            KeySchemaElement::builder()
                .attribute_name("file_id")
                .key_type(KeyType::Hash)
                .build()
                .expect("valid file_id key"),
            KeySchemaElement::builder()
                .attribute_name("version")
                .key_type(KeyType::Range)
                .build()
                .expect("valid version key"),
        ],
    )
    .await;
    create_table(
        &meta.client,
        &meta.shares_table,
        vec![AttributeDefinition::builder()
            .attribute_name("id")
            .attribute_type(ScalarAttributeType::S)
            .build()
            .expect("valid id definition")],
        vec![KeySchemaElement::builder()
            .attribute_name("id")
            .key_type(KeyType::Hash)
            .build()
            .expect("valid id key")],
    )
    .await;

    for table in [
        &meta.files_table,
        &meta.folders_table,
        &meta.versions_table,
        &meta.shares_table,
    ] {
        for _ in 0..30 {
            let active = meta
                .client
                .describe_table()
                .table_name(table)
                .send()
                .await
                .ok()
                .and_then(|output| output.table)
                .and_then(|table| table.table_status)
                .is_some_and(|status| status == TableStatus::Active);
            if active {
                break;
            }
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
    }
}

pub async fn build_app(
    config: AppConfig,
    s3: S3Client,
    meta: MetadataClient,
    events: EventPublisher,
    redis_cm: ConnectionManager,
) -> impl Service<actix_http::Request, Response = ServiceResponse<BoxBody>, Error = Error> {
    actix_web::test::init_service(
        App::new()
            .app_data(web::Data::new(config))
            .app_data(web::Data::new(s3))
            .app_data(web::Data::new(meta))
            .app_data(web::Data::new(events))
            .app_data(web::Data::new(redis_cm))
            .configure(file_service::configure_routes),
    )
    .await
}

pub async fn clients(
    endpoint: &str,
    redis_url: &str,
) -> (
    AppConfig,
    S3Client,
    MetadataClient,
    EventPublisher,
    ConnectionManager,
) {
    let aws = test_aws_config(endpoint);
    let config = AppConfig {
        server: ServerConfig {
            port: 0,
            max_upload_bytes: 1024,
        },
        aws: aws.clone(),
        sns: SnsConfig { topic_arn: None },
    };
    let s3 = S3Client::new(&aws).await;
    let meta = MetadataClient::new(&aws).await;
    let events = EventPublisher::new(&config.sns, &aws).await;
    let redis = redis::Client::open(redis_url).expect("valid Redis URL");
    let redis_cm = ConnectionManager::new(redis)
        .await
        .expect("Redis should be reachable");
    (config, s3, meta, events, redis_cm)
}

pub fn json_error(body: &serde_json::Value) -> &str {
    body["error"].as_str().expect("error field is a string")
}

pub fn multipart_body(boundary: &str, owner_id: Option<&str>, file: Option<&[u8]>) -> Vec<u8> {
    let mut body = Vec::new();
    if let Some(owner_id) = owner_id {
        body.extend_from_slice(
            format!(
                "--{boundary}\r\nContent-Disposition: form-data; name=\"owner_id\"\r\n\r\n{owner_id}\r\n"
            )
            .as_bytes(),
        );
    }
    if let Some(file) = file {
        body.extend_from_slice(
            format!(
                "--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"test.txt\"\r\nContent-Type: text/plain\r\n\r\n"
            )
            .as_bytes(),
        );
        body.extend_from_slice(file);
        body.extend_from_slice(b"\r\n");
    }
    body.extend_from_slice(format!("--{boundary}--\r\n").as_bytes());
    body
}
