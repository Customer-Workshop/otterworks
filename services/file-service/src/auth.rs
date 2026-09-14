use actix_web::body::MessageBody;
use actix_web::dev::{ServiceRequest, ServiceResponse};
use actix_web::middleware::Next;
use actix_web::{web, Error, HttpRequest};
use jsonwebtoken::{decode, AlgorithmFamily, DecodingKey, Validation};
use serde::Deserialize;
use uuid::Uuid;

use crate::config::{AppConfig, AuthConfig};
use crate::errors::ServiceError;

#[derive(Debug, Deserialize)]
struct Claims {
    sub: Option<String>,
    user_id: Option<String>,
    #[serde(rename = "type")]
    token_type: Option<String>,
}

/// Middleware for the `/api/v1` scopes: every request must carry a valid bearer
/// JWT, so object routes that do not need the caller's identity are still not
/// reachable anonymously off the gateway path.
pub async fn require_bearer(
    req: ServiceRequest,
    next: Next<impl MessageBody>,
) -> Result<ServiceResponse<impl MessageBody>, Error> {
    let config = req
        .app_data::<web::Data<AppConfig>>()
        .cloned()
        .ok_or_else(|| ServiceError::Internal("AppConfig is not registered".into()))?;
    authenticated_user(req.request(), &config.auth)?;
    next.call(req).await
}

/// Identity of the caller, taken from the signed `Authorization: Bearer` JWT.
///
/// The token is verified here, in-service, with the shared `JWT_SECRET`. The
/// `X-User-ID` header and any `owner_id` carried in the query string or request
/// body are never used as identity: off the gateway path they are chosen by the
/// caller, so trusting them lets anyone act as any user.
pub fn authenticated_user(req: &HttpRequest, auth: &AuthConfig) -> Result<Uuid, ServiceError> {
    let secret = auth
        .jwt_secret
        .as_deref()
        .ok_or_else(|| ServiceError::Internal("JWT_SECRET is not configured".into()))?;

    let token = bearer_token(req)
        .ok_or_else(|| ServiceError::Unauthorized("missing bearer token".into()))?;

    let validation = Validation::new_for_family(AlgorithmFamily::Hmac);
    let data = decode::<Claims>(
        token,
        &DecodingKey::from_secret(secret.as_bytes()),
        &validation,
    )
    .map_err(|e| ServiceError::Unauthorized(format!("invalid token: {e}")))?;

    if data.claims.token_type.as_deref() == Some("refresh") {
        return Err(ServiceError::Unauthorized(
            "refresh tokens cannot be used for API access".into(),
        ));
    }

    data.claims
        .sub
        .or(data.claims.user_id)
        .and_then(|s| s.trim().parse::<Uuid>().ok())
        .ok_or_else(|| ServiceError::Unauthorized("token carries no user identity".into()))
}

fn bearer_token(req: &HttpRequest) -> Option<&str> {
    let value = req.headers().get("Authorization")?.to_str().ok()?;
    let (scheme, token) = value.trim().split_once(' ')?;
    if !scheme.eq_ignore_ascii_case("bearer") {
        return None;
    }
    Some(token.trim()).filter(|t| !t.is_empty())
}

#[cfg(test)]
mod tests {
    use super::*;
    use actix_web::test::TestRequest;
    use jsonwebtoken::{encode, get_current_timestamp, Algorithm, EncodingKey, Header};
    use serde::Serialize;

    const SECRET: &str = "file-service-test-secret";
    const VICTIM: &str = "11111111-1111-1111-1111-111111111111";
    const ATTACKER: &str = "22222222-2222-2222-2222-222222222222";

    #[derive(Serialize)]
    struct TestClaims<'a> {
        sub: Option<&'a str>,
        user_id: Option<&'a str>,
        #[serde(rename = "type", skip_serializing_if = "Option::is_none")]
        token_type: Option<&'a str>,
        exp: u64,
    }

    fn config(secret: Option<&str>) -> AuthConfig {
        AuthConfig {
            jwt_secret: secret.map(str::to_owned),
        }
    }

    fn token(
        secret: &str,
        alg: Algorithm,
        sub: Option<&str>,
        user_id: Option<&str>,
        exp: u64,
    ) -> String {
        encode(
            &Header::new(alg),
            &TestClaims {
                sub,
                user_id,
                token_type: None,
                exp,
            },
            &EncodingKey::from_secret(secret.as_bytes()),
        )
        .unwrap()
    }

    fn typed_token(sub: &str, token_type: &str) -> String {
        encode(
            &Header::new(Algorithm::HS256),
            &TestClaims {
                sub: Some(sub),
                user_id: None,
                token_type: Some(token_type),
                exp: get_current_timestamp() + 300,
            },
            &EncodingKey::from_secret(SECRET.as_bytes()),
        )
        .unwrap()
    }

    fn valid_token(sub: &str) -> String {
        token(
            SECRET,
            Algorithm::HS256,
            Some(sub),
            None,
            get_current_timestamp() + 300,
        )
    }

    fn assert_unauthorized(result: Result<Uuid, ServiceError>) {
        assert!(
            matches!(result, Err(ServiceError::Unauthorized(_))),
            "expected Unauthorized, got {result:?}"
        );
    }

    #[test]
    fn identity_comes_from_the_verified_token() {
        let req = TestRequest::default()
            .insert_header(("Authorization", format!("Bearer {}", valid_token(ATTACKER))))
            .to_http_request();

        assert_eq!(
            authenticated_user(&req, &config(Some(SECRET))).unwrap(),
            ATTACKER.parse::<Uuid>().unwrap()
        );
    }

    #[test]
    fn x_user_id_header_alone_is_rejected() {
        let req = TestRequest::default()
            .insert_header(("X-User-ID", VICTIM))
            .to_http_request();

        assert_unauthorized(authenticated_user(&req, &config(Some(SECRET))));
    }

    #[test]
    fn x_user_id_header_cannot_override_the_token_identity() {
        let req = TestRequest::default()
            .insert_header(("Authorization", format!("Bearer {}", valid_token(ATTACKER))))
            .insert_header(("X-User-ID", VICTIM))
            .to_http_request();

        assert_eq!(
            authenticated_user(&req, &config(Some(SECRET))).unwrap(),
            ATTACKER.parse::<Uuid>().unwrap()
        );
    }

    #[test]
    fn token_signed_with_another_secret_is_rejected() {
        let forged = token(
            "not-the-real-secret",
            Algorithm::HS256,
            Some(VICTIM),
            None,
            get_current_timestamp() + 300,
        );
        let req = TestRequest::default()
            .insert_header(("Authorization", format!("Bearer {forged}")))
            .to_http_request();

        assert_unauthorized(authenticated_user(&req, &config(Some(SECRET))));
    }

    #[test]
    fn expired_token_is_rejected() {
        let expired = token(
            SECRET,
            Algorithm::HS256,
            Some(VICTIM),
            None,
            get_current_timestamp() - 3600,
        );
        let req = TestRequest::default()
            .insert_header(("Authorization", format!("Bearer {expired}")))
            .to_http_request();

        assert_unauthorized(authenticated_user(&req, &config(Some(SECRET))));
    }

    #[test]
    fn refresh_token_is_rejected_but_access_token_is_accepted() {
        let refresh = TestRequest::default()
            .insert_header((
                "Authorization",
                format!("Bearer {}", typed_token(VICTIM, "refresh")),
            ))
            .to_http_request();
        assert_unauthorized(authenticated_user(&refresh, &config(Some(SECRET))));

        let access = TestRequest::default()
            .insert_header((
                "Authorization",
                format!("Bearer {}", typed_token(VICTIM, "access")),
            ))
            .to_http_request();
        assert_eq!(
            authenticated_user(&access, &config(Some(SECRET))).unwrap(),
            VICTIM.parse::<Uuid>().unwrap()
        );
    }

    #[actix_web::test]
    async fn object_routes_require_a_bearer_token() {
        use actix_web::middleware::from_fn;
        use actix_web::{http::StatusCode, test, App, HttpResponse};

        let app = test::init_service(
            App::new()
                .app_data(web::Data::new(AppConfig {
                    auth: config(Some(SECRET)),
                    ..AppConfig::from_env()
                }))
                .service(
                    web::scope("/api/v1/files")
                        .wrap(from_fn(require_bearer))
                        .route("/{file_id}", web::get().to(HttpResponse::Ok)),
                ),
        )
        .await;

        let anonymous = test::TestRequest::get()
            .uri("/api/v1/files/some-id")
            .insert_header(("X-User-ID", VICTIM))
            .to_request();
        let status = match test::try_call_service(&app, anonymous).await {
            Ok(resp) => resp.status(),
            Err(err) => err.error_response().status(),
        };
        assert_eq!(status, StatusCode::UNAUTHORIZED);

        let authenticated = test::TestRequest::get()
            .uri("/api/v1/files/some-id")
            .insert_header(("Authorization", format!("Bearer {}", valid_token(ATTACKER))))
            .to_request();
        assert_eq!(
            test::call_service(&app, authenticated).await.status(),
            StatusCode::OK
        );
    }

    #[test]
    fn falls_back_to_user_id_claim_and_accepts_hs384() {
        let t = token(
            SECRET,
            Algorithm::HS384,
            None,
            Some(VICTIM),
            get_current_timestamp() + 300,
        );
        let req = TestRequest::default()
            .insert_header(("Authorization", format!("Bearer {t}")))
            .to_http_request();

        assert_eq!(
            authenticated_user(&req, &config(Some(SECRET))).unwrap(),
            VICTIM.parse::<Uuid>().unwrap()
        );
    }

    #[test]
    fn missing_secret_fails_closed() {
        let req = TestRequest::default()
            .insert_header(("Authorization", format!("Bearer {}", valid_token(ATTACKER))))
            .insert_header(("X-User-ID", VICTIM))
            .to_http_request();

        let result = authenticated_user(&req, &config(None));
        assert!(
            matches!(result, Err(ServiceError::Internal(_))),
            "expected Internal, got {result:?}"
        );
    }
}
