use actix_web::{body::to_bytes, http::StatusCode, test, App};
use file_service::configure_routes;

#[actix_rt::test]
async fn health_and_metrics_routes_are_available_without_infra() {
    let app = test::init_service(App::new().configure(configure_routes)).await;

    let response =
        test::call_service(&app, test::TestRequest::get().uri("/health").to_request()).await;
    assert_eq!(response.status(), StatusCode::OK);
    let body: serde_json::Value =
        serde_json::from_slice(&to_bytes(response.into_body()).await.unwrap()).unwrap();
    assert_eq!(body["status"], "healthy");
    assert_eq!(body["service"], "file-service");

    let response =
        test::call_service(&app, test::TestRequest::get().uri("/metrics").to_request()).await;
    assert_eq!(response.status(), StatusCode::OK);
    assert!(response
        .headers()
        .get("content-type")
        .and_then(|value| value.to_str().ok())
        .is_some_and(|value| value.starts_with("text/plain")));
}
