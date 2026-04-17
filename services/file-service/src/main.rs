use actix_web::{web, App, HttpServer, HttpResponse, middleware};
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

mod config;
mod handlers;
mod models;
mod storage;

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    dotenvy::dotenv().ok();

    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::new(
            std::env::var("RUST_LOG").unwrap_or_else(|_| "file_service=debug,actix_web=info".into()),
        ))
        .with(tracing_subscriber::fmt::layer().json())
        .init();

    let aws_config = config::AwsConfig::from_env();
    let s3_client = storage::S3Client::new(&aws_config).await;
    let dynamo_client = storage::DynamoClient::new(&aws_config).await;

    let port = std::env::var("PORT").unwrap_or_else(|_| "8082".into());
    tracing::info!(port = %port, "File Service starting");

    HttpServer::new(move || {
        App::new()
            .wrap(tracing_actix_web::TracingLogger::default())
            .wrap(middleware::Compress::default())
            .app_data(web::Data::new(s3_client.clone()))
            .app_data(web::Data::new(dynamo_client.clone()))
            .route("/health", web::get().to(handlers::health))
            .route("/metrics", web::get().to(handlers::metrics))
            .service(
                web::scope("/api/v1/files")
                    .route("", web::post().to(handlers::upload_file))
                    .route("", web::get().to(handlers::list_files))
                    .route("/{file_id}", web::get().to(handlers::get_file))
                    .route("/{file_id}", web::delete().to(handlers::delete_file))
                    .route("/{file_id}/download", web::get().to(handlers::download_file))
                    .route("/{file_id}/versions", web::get().to(handlers::list_versions))
            )
            .service(
                web::scope("/api/v1/folders")
                    .route("", web::post().to(handlers::create_folder))
                    .route("/{folder_id}", web::get().to(handlers::get_folder))
                    .route("/{folder_id}", web::put().to(handlers::update_folder))
                    .route("/{folder_id}", web::delete().to(handlers::delete_folder))
            )
    })
    .bind(format!("0.0.0.0:{}", port))?
    .run()
    .await
}
