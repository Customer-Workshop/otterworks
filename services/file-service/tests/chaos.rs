mod common;

use actix_web::{body::to_bytes, http::header::CONTENT_TYPE, http::StatusCode, test};
use file_service::handlers::{
    chaos_active, effective_upload_bucket, CHAOS_NONEXISTENT_BUCKET, CHAOS_UPLOAD_S3_ERROR_FLAG,
};
use uuid::Uuid;

#[actix_rt::test]
async fn chaos_flag_controls_effective_upload_bucket() {
    let Some(redis_url) = common::redis_url() else {
        eprintln!("skipping: REDIS_URL not set");
        return;
    };
    let client = redis::Client::open(redis_url).expect("valid Redis URL");
    let mut manager = redis::aio::ConnectionManager::new(client)
        .await
        .expect("Redis should be reachable");

    let _: () = redis::cmd("SET")
        .arg(CHAOS_UPLOAD_S3_ERROR_FLAG)
        .arg(1)
        .arg("EX")
        .arg(30)
        .query_async(&mut manager)
        .await
        .expect("set chaos flag");
    let active = chaos_active(&mut manager, CHAOS_UPLOAD_S3_ERROR_FLAG).await;
    let _: () = redis::cmd("DEL")
        .arg(CHAOS_UPLOAD_S3_ERROR_FLAG)
        .query_async(&mut manager)
        .await
        .expect("clear chaos flag");
    assert!(active);
    assert_eq!(
        effective_upload_bucket(active, "otterworks-files"),
        CHAOS_NONEXISTENT_BUCKET
    );
    assert!(!chaos_active(&mut manager, CHAOS_UPLOAD_S3_ERROR_FLAG).await);
    assert_eq!(
        effective_upload_bucket(false, "otterworks-files"),
        "otterworks-files"
    );
}

#[actix_rt::test]
async fn chaos_flag_causes_upload_failure_then_normal_upload() {
    let Some(endpoint) = common::aws_endpoint() else {
        eprintln!("skipping: AWS_ENDPOINT_URL not set");
        return;
    };
    let Some(redis_url) = common::redis_url() else {
        eprintln!("skipping: REDIS_URL not set");
        return;
    };
    let (config, s3, meta, events, mut redis_cm) = common::clients(&endpoint, &redis_url).await;
    common::ensure_infra(&s3, &meta).await;
    let app = common::build_app(config, s3, meta, events, redis_cm.clone()).await;
    let owner = Uuid::new_v4();
    let boundary = format!("boundary-{}", Uuid::new_v4());
    let body = common::multipart_body(&boundary, Some(&owner.to_string()), Some(b"chaos"));
    let _: () = redis::cmd("SET")
        .arg(CHAOS_UPLOAD_S3_ERROR_FLAG)
        .arg(1)
        .arg("EX")
        .arg(30)
        .query_async(&mut redis_cm)
        .await
        .expect("set chaos flag");
    let response = test::call_service(
        &app,
        test::TestRequest::post()
            .uri("/api/v1/files/upload")
            .insert_header((
                CONTENT_TYPE,
                format!("multipart/form-data; boundary={boundary}"),
            ))
            .set_payload(body)
            .to_request(),
    )
    .await;
    let status = response.status();
    let response_body: serde_json::Value =
        serde_json::from_slice(&to_bytes(response.into_body()).await.unwrap()).unwrap();
    let _: () = redis::cmd("DEL")
        .arg(CHAOS_UPLOAD_S3_ERROR_FLAG)
        .query_async(&mut redis_cm)
        .await
        .expect("clear chaos flag");
    assert_eq!(status, StatusCode::INTERNAL_SERVER_ERROR);
    assert_eq!(common::json_error(&response_body), "storage_error");

    let boundary = format!("boundary-{}", Uuid::new_v4());
    let body = common::multipart_body(&boundary, Some(&owner.to_string()), Some(b"normal"));
    let response = test::call_service(
        &app,
        test::TestRequest::post()
            .uri("/api/v1/files/upload")
            .insert_header((
                CONTENT_TYPE,
                format!("multipart/form-data; boundary={boundary}"),
            ))
            .set_payload(body)
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::CREATED);
}
