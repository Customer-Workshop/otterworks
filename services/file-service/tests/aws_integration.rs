mod common;

use actix_web::{
    body::to_bytes,
    http::{header::CONTENT_TYPE, StatusCode},
    test,
};
use file_service::models::FileMetadata;
use uuid::Uuid;

async fn setup() -> Option<(
    impl actix_web::dev::Service<
        actix_http::Request,
        Response = actix_web::dev::ServiceResponse<actix_web::body::BoxBody>,
        Error = actix_web::Error,
    >,
    Uuid,
)> {
    let Some(endpoint) = common::aws_endpoint() else {
        eprintln!("skipping: AWS_ENDPOINT_URL not set");
        return None;
    };
    let Some(redis_url) = common::redis_url() else {
        eprintln!("skipping: REDIS_URL not set");
        return None;
    };
    let (config, s3, meta, events, redis_cm) = common::clients(&endpoint, &redis_url).await;
    common::ensure_infra(&s3, &meta).await;
    let app = common::build_app(config, s3, meta, events, redis_cm).await;
    Some((app, Uuid::new_v4()))
}

async fn upload(
    app: &impl actix_web::dev::Service<
        actix_http::Request,
        Response = actix_web::dev::ServiceResponse<actix_web::body::BoxBody>,
        Error = actix_web::Error,
    >,
    owner: Uuid,
    header_owner: Option<Uuid>,
    field_owner: Option<Uuid>,
    bytes: &[u8],
) -> (StatusCode, serde_json::Value) {
    let boundary = format!("boundary-{}", Uuid::new_v4());
    let body = common::multipart_body(
        &boundary,
        field_owner.as_ref().map(Uuid::to_string).as_deref(),
        Some(bytes),
    );
    let mut request = test::TestRequest::post()
        .uri("/api/v1/files/upload")
        .insert_header((
            CONTENT_TYPE,
            format!("multipart/form-data; boundary={boundary}"),
        ));
    if let Some(header_owner) = header_owner {
        request = request.insert_header(("X-User-ID", header_owner.to_string()));
    } else if field_owner.is_none() {
        request = request.insert_header(("X-User-ID", owner.to_string()));
    }
    let response = test::call_service(app, request.set_payload(body).to_request()).await;
    let status = response.status();
    let body: serde_json::Value =
        serde_json::from_slice(&to_bytes(response.into_body()).await.unwrap()).unwrap();
    (status, body)
}

#[actix_rt::test]
async fn upload_honors_identity_header_and_validates_input() {
    let Some((app, owner)) = setup().await else {
        return;
    };
    let header_owner = Uuid::new_v4();
    let field_owner = Uuid::new_v4();
    let (status, body) = upload(&app, owner, Some(header_owner), Some(field_owner), b"hello").await;
    assert_eq!(status, StatusCode::CREATED);
    assert_eq!(body["file"]["owner_id"], header_owner.to_string());
    assert_eq!(body["file"]["size_bytes"], 5);
    assert_eq!(body["file"]["name"], "test.txt");

    let boundary = format!("boundary-{}", Uuid::new_v4());
    let no_owner = common::multipart_body(&boundary, None, Some(b"hello"));
    let response = test::call_service(
        &app,
        test::TestRequest::post()
            .uri("/api/v1/files/upload")
            .insert_header((
                CONTENT_TYPE,
                format!("multipart/form-data; boundary={boundary}"),
            ))
            .set_payload(no_owner)
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    let body: serde_json::Value =
        serde_json::from_slice(&to_bytes(response.into_body()).await.unwrap()).unwrap();
    assert_eq!(common::json_error(&body), "bad_request");

    let (status, body) = upload(&app, owner, Some(owner), None, &vec![b'x'; 2000]).await;
    assert_eq!(status, StatusCode::PAYLOAD_TOO_LARGE);
    assert_eq!(common::json_error(&body), "file_too_large");

    let boundary = format!("boundary-{}", Uuid::new_v4());
    let no_file = common::multipart_body(&boundary, Some(&owner.to_string()), None);
    let response = test::call_service(
        &app,
        test::TestRequest::post()
            .uri("/api/v1/files/upload")
            .insert_header((
                CONTENT_TYPE,
                format!("multipart/form-data; boundary={boundary}"),
            ))
            .set_payload(no_file)
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
}

#[actix_rt::test]
async fn file_lifecycle_and_owner_listing_work() {
    let Some((app, owner)) = setup().await else {
        return;
    };
    let (status, body) = upload(&app, owner, Some(owner), None, b"lifecycle").await;
    assert_eq!(status, StatusCode::CREATED);
    let file: FileMetadata = serde_json::from_value(body["file"].clone()).unwrap();
    let path = format!("/api/v1/files/{}", file.id);

    let response = test::call_service(&app, test::TestRequest::get().uri(&path).to_request()).await;
    assert_eq!(response.status(), StatusCode::OK);
    let metadata: serde_json::Value =
        serde_json::from_slice(&to_bytes(response.into_body()).await.unwrap()).unwrap();
    assert_eq!(metadata["id"], file.id.to_string());

    let response = test::call_service(
        &app,
        test::TestRequest::get()
            .uri(&format!("{path}/download"))
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    let download: serde_json::Value =
        serde_json::from_slice(&to_bytes(response.into_body()).await.unwrap()).unwrap();
    assert!(download["url"].as_str().unwrap().contains(&file.s3_key));

    let response = test::call_service(
        &app,
        test::TestRequest::get()
            .uri(&format!("/api/v1/files?owner_id={owner}"))
            .insert_header(("X-User-ID", owner.to_string()))
            .to_request(),
    )
    .await;
    let listing: serde_json::Value =
        serde_json::from_slice(&to_bytes(response.into_body()).await.unwrap()).unwrap();
    assert!(listing["total"].as_u64().unwrap() >= 1);

    let response = test::call_service(
        &app,
        test::TestRequest::patch()
            .uri(&format!("{path}/rename"))
            .set_json(serde_json::json!({"name": "renamed.txt"}))
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    let renamed: serde_json::Value =
        serde_json::from_slice(&to_bytes(response.into_body()).await.unwrap()).unwrap();
    assert_eq!(renamed["name"], "renamed.txt");

    let response = test::call_service(
        &app,
        test::TestRequest::post()
            .uri(&format!("{path}/trash"))
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    let response = test::call_service(
        &app,
        test::TestRequest::get()
            .uri("/api/v1/files/trash")
            .insert_header(("X-User-ID", owner.to_string()))
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    let trash: serde_json::Value =
        serde_json::from_slice(&to_bytes(response.into_body()).await.unwrap()).unwrap();
    assert!(trash["files"]
        .as_array()
        .unwrap()
        .iter()
        .any(|item| item["id"] == file.id.to_string()));

    let response = test::call_service(
        &app,
        test::TestRequest::post()
            .uri(&format!("{path}/restore"))
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    let response =
        test::call_service(&app, test::TestRequest::delete().uri(&path).to_request()).await;
    assert_eq!(response.status(), StatusCode::NO_CONTENT);
    let response = test::call_service(&app, test::TestRequest::get().uri(&path).to_request()).await;
    assert_eq!(response.status(), StatusCode::NOT_FOUND);
    let body: serde_json::Value =
        serde_json::from_slice(&to_bytes(response.into_body()).await.unwrap()).unwrap();
    assert_eq!(common::json_error(&body), "file_not_found");
}

#[actix_rt::test]
async fn sharing_is_idempotent_and_updates_permission() {
    let Some((app, owner)) = setup().await else {
        return;
    };
    let shared_with = Uuid::new_v4();
    let (status, body) = upload(&app, owner, Some(owner), None, b"shared").await;
    assert_eq!(status, StatusCode::CREATED);
    let file_id = body["file"]["id"].as_str().unwrap();
    let share_body = serde_json::json!({
        "shared_with": shared_with,
        "permission": "viewer",
        "shared_by": owner
    });

    let response = test::call_service(
        &app,
        test::TestRequest::post()
            .uri(&format!("/api/v1/files/{file_id}/share"))
            .set_json(&share_body)
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::CREATED);
    let response = test::call_service(
        &app,
        test::TestRequest::post()
            .uri(&format!("/api/v1/files/{file_id}/share"))
            .set_json(&share_body)
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);

    let editor_body = serde_json::json!({
        "shared_with": shared_with,
        "permission": "editor",
        "shared_by": owner
    });
    let response = test::call_service(
        &app,
        test::TestRequest::post()
            .uri(&format!("/api/v1/files/{file_id}/share"))
            .set_json(&editor_body)
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    let updated: serde_json::Value =
        serde_json::from_slice(&to_bytes(response.into_body()).await.unwrap()).unwrap();
    assert_eq!(updated["share"]["permission"], "editor");

    let response = test::call_service(
        &app,
        test::TestRequest::get()
            .uri("/api/v1/files/shared")
            .insert_header(("X-User-ID", shared_with.to_string()))
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    let shared: serde_json::Value =
        serde_json::from_slice(&to_bytes(response.into_body()).await.unwrap()).unwrap();
    assert!(shared["files"]
        .as_array()
        .unwrap()
        .iter()
        .any(|item| item["id"] == file_id));

    let uri = format!("/api/v1/files/{file_id}/share/{shared_with}");
    let response =
        test::call_service(&app, test::TestRequest::delete().uri(&uri).to_request()).await;
    assert_eq!(response.status(), StatusCode::NO_CONTENT);
    let response =
        test::call_service(&app, test::TestRequest::delete().uri(&uri).to_request()).await;
    assert_eq!(response.status(), StatusCode::NOT_FOUND);
    let body: serde_json::Value =
        serde_json::from_slice(&to_bytes(response.into_body()).await.unwrap()).unwrap();
    assert_eq!(common::json_error(&body), "share_not_found");
}

#[actix_rt::test]
async fn folder_crud_and_owner_listing_work() {
    let Some((app, owner)) = setup().await else {
        return;
    };
    let response = test::call_service(
        &app,
        test::TestRequest::post()
            .uri("/api/v1/folders")
            .set_json(serde_json::json!({"name": "Documents", "owner_id": owner}))
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::CREATED);
    let folder: serde_json::Value =
        serde_json::from_slice(&to_bytes(response.into_body()).await.unwrap()).unwrap();
    let folder_id = folder["id"].as_str().unwrap().to_string();

    let response = test::call_service(
        &app,
        test::TestRequest::get()
            .uri(&format!("/api/v1/folders/{folder_id}"))
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);

    let response = test::call_service(
        &app,
        test::TestRequest::put()
            .uri(&format!("/api/v1/folders/{folder_id}"))
            .set_json(serde_json::json!({"name": "Renamed"}))
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    let renamed: serde_json::Value =
        serde_json::from_slice(&to_bytes(response.into_body()).await.unwrap()).unwrap();
    assert_eq!(renamed["name"], "Renamed");

    let response = test::call_service(
        &app,
        test::TestRequest::get()
            .uri(&format!("/api/v1/folders?owner_id={owner}"))
            .insert_header(("X-User-ID", owner.to_string()))
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::OK);
    let folders: serde_json::Value =
        serde_json::from_slice(&to_bytes(response.into_body()).await.unwrap()).unwrap();
    assert!(folders["folders"]
        .as_array()
        .unwrap()
        .iter()
        .any(|item| item["id"] == folder_id));

    let response = test::call_service(
        &app,
        test::TestRequest::delete()
            .uri(&format!("/api/v1/folders/{folder_id}"))
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::NO_CONTENT);
    let response = test::call_service(
        &app,
        test::TestRequest::get()
            .uri(&format!("/api/v1/folders/{folder_id}"))
            .to_request(),
    )
    .await;
    assert_eq!(response.status(), StatusCode::NOT_FOUND);
    let body: serde_json::Value =
        serde_json::from_slice(&to_bytes(response.into_body()).await.unwrap()).unwrap();
    assert_eq!(common::json_error(&body), "folder_not_found");
}
