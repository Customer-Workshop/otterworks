use crate::config::AwsConfig;

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
        let client = aws_sdk_s3::Client::new(&aws_config);

        Self {
            client,
            bucket: config.s3_bucket.clone(),
        }
    }
}

#[derive(Clone)]
pub struct DynamoClient {
    pub client: aws_sdk_dynamodb::Client,
    pub table: String,
}

impl DynamoClient {
    pub async fn new(config: &AwsConfig) -> Self {
        let mut aws_config_builder = aws_config::defaults(aws_config::BehaviorVersion::latest())
            .region(aws_config::Region::new(config.region.clone()));

        if let Some(endpoint) = &config.endpoint_url {
            aws_config_builder = aws_config_builder.endpoint_url(endpoint);
        }

        let aws_config = aws_config_builder.load().await;
        let client = aws_sdk_dynamodb::Client::new(&aws_config);

        Self {
            client,
            table: config.dynamodb_table.clone(),
        }
    }
}
