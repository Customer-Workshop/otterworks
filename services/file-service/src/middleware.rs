use actix_web::dev::{Service, ServiceRequest, ServiceResponse, Transform};
use actix_web::Error;
use futures_util::future::{ok, LocalBoxFuture, Ready};
use std::task::{Context, Poll};
use uuid::Uuid;

use lazy_static::lazy_static;
use prometheus::{
    register_histogram_vec, register_int_counter_vec, Encoder, HistogramVec, IntCounterVec,
    TextEncoder,
};

lazy_static! {
    pub static ref HTTP_REQUESTS_TOTAL: IntCounterVec = register_int_counter_vec!(
        "http_requests_total",
        "Total HTTP requests",
        &["method", "path", "status"]
    )
    .expect("metric can be created");
    pub static ref HTTP_REQUEST_DURATION: HistogramVec = register_histogram_vec!(
        "http_request_duration_seconds",
        "HTTP request duration in seconds",
        &["method", "path"],
        vec![0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
    )
    .expect("metric can be created");
}

pub fn render_metrics() -> String {
    let encoder = TextEncoder::new();
    let metric_families = prometheus::gather();
    let mut buffer = Vec::new();
    encoder.encode(&metric_families, &mut buffer).unwrap();
    String::from_utf8(buffer).unwrap()
}

// -- Request ID Middleware --

pub struct RequestId;

impl<S, B> Transform<S, ServiceRequest> for RequestId
where
    S: Service<ServiceRequest, Response = ServiceResponse<B>, Error = Error>,
    S::Future: 'static,
    B: 'static,
{
    type Response = ServiceResponse<B>;
    type Error = Error;
    type Transform = RequestIdMiddleware<S>;
    type InitError = ();
    type Future = Ready<Result<Self::Transform, Self::InitError>>;

    fn new_transform(&self, service: S) -> Self::Future {
        ok(RequestIdMiddleware { service })
    }
}

pub struct RequestIdMiddleware<S> {
    service: S,
}

impl<S, B> Service<ServiceRequest> for RequestIdMiddleware<S>
where
    S: Service<ServiceRequest, Response = ServiceResponse<B>, Error = Error>,
    S::Future: 'static,
    B: 'static,
{
    type Response = ServiceResponse<B>;
    type Error = Error;
    type Future = LocalBoxFuture<'static, Result<Self::Response, Self::Error>>;

    fn poll_ready(&self, cx: &mut Context<'_>) -> Poll<Result<(), Self::Error>> {
        self.service.poll_ready(cx)
    }

    fn call(&self, req: ServiceRequest) -> Self::Future {
        let request_id = req
            .headers()
            .get("x-request-id")
            .and_then(|v| v.to_str().ok())
            .map(|s| s.to_string())
            .unwrap_or_else(|| Uuid::new_v4().to_string());

        let method = req.method().to_string();
        let path = req
            .match_pattern()
            .unwrap_or_else(|| "unmatched".to_string());
        let start = std::time::Instant::now();

        let fut = self.service.call(req);

        Box::pin(async move {
            let res = fut.await?;
            let elapsed = start.elapsed().as_secs_f64();
            let status = res.status().as_u16().to_string();

            HTTP_REQUESTS_TOTAL
                .with_label_values(&[&method, &path, &status])
                .inc();
            HTTP_REQUEST_DURATION
                .with_label_values(&[&method, &path])
                .observe(elapsed);

            tracing::info!(
                request_id = %request_id,
                method = %method,
                path = %path,
                status = %status,
                duration_ms = %(elapsed * 1000.0),
                "Request completed"
            );

            Ok(res)
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn render_metrics_returns_non_empty_string() {
        // Ensure at least one metric family is registered by touching the counters.
        HTTP_REQUESTS_TOTAL
            .with_label_values(&["GET", "/ping", "200"])
            .inc();
        let output = render_metrics();
        assert!(!output.is_empty());
    }

    #[test]
    fn render_metrics_contains_prometheus_format() {
        // Force the lazy_static metrics to be initialised by touching them.
        HTTP_REQUESTS_TOTAL
            .with_label_values(&["GET", "/health", "200"])
            .inc();
        HTTP_REQUEST_DURATION
            .with_label_values(&["GET", "/health"])
            .observe(0.005);

        let output = render_metrics();
        assert!(
            output.contains("http_requests_total") || output.contains("# HELP"),
            "expected prometheus metric names or comments"
        );
    }

    #[test]
    fn http_requests_total_increment_does_not_panic() {
        HTTP_REQUESTS_TOTAL
            .with_label_values(&["POST", "/upload", "201"])
            .inc();
        HTTP_REQUESTS_TOTAL
            .with_label_values(&["DELETE", "/files/123", "204"])
            .inc();
    }

    #[test]
    fn http_requests_total_counter_registered() {
        let val = HTTP_REQUESTS_TOTAL.with_label_values(&["GET", "/test_registered", "200"]);
        val.inc();
        assert!(val.get() >= 1);
    }

    #[test]
    fn http_request_duration_observe_does_not_panic() {
        HTTP_REQUEST_DURATION
            .with_label_values(&["GET", "/files"])
            .observe(0.1);
        HTTP_REQUEST_DURATION
            .with_label_values(&["PUT", "/files/move"])
            .observe(1.5);
    }

    #[test]
    fn http_request_duration_histogram_registered() {
        let hist = HTTP_REQUEST_DURATION.with_label_values(&["GET", "/test_hist_registered"]);
        hist.observe(0.042);
        let count = hist.get_sample_count();
        assert!(count >= 1);
    }

    #[test]
    fn render_metrics_includes_request_counter_after_increment() {
        HTTP_REQUESTS_TOTAL
            .with_label_values(&["GET", "/metrics_check", "200"])
            .inc();
        let output = render_metrics();
        assert!(output.contains("http_requests_total"));
    }

    #[test]
    fn render_metrics_includes_duration_histogram_after_observe() {
        HTTP_REQUEST_DURATION
            .with_label_values(&["GET", "/duration_check"])
            .observe(0.01);
        let output = render_metrics();
        assert!(output.contains("http_request_duration_seconds"));
    }
}
