package proxy

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/rs/zerolog"

	"github.com/Cognition-Partner-Workshops/otterworks/services/api-gateway/internal/middleware"
)

func testRouterConfig(routes []Route) RouterConfig {
	return RouterConfig{
		Routes: routes,
		CBManager: NewCircuitBreakerManager(CircuitBreakerConfig{
			MaxRequests:  1,
			Interval:     time.Minute,
			Timeout:      time.Minute,
			FailureRatio: 0.6,
		}),
		Logger: zerolog.Nop(),
	}
}

func TestRouterProxiesToBackendPreservingPath(t *testing.T) {
	var gotPath string
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"ok":true}`))
	}))
	defer backend.Close()

	r := NewRouter(testRouterConfig([]Route{{Prefix: "/api/v1/files", TargetURL: backend.URL}}))
	srv := httptest.NewServer(r)
	defer srv.Close()

	resp, err := http.Get(srv.URL + "/api/v1/files/123/versions")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", resp.StatusCode)
	}
	if gotPath != "/api/v1/files/123/versions" {
		t.Fatalf("backend received path %q, want full original path", gotPath)
	}
	body, _ := io.ReadAll(resp.Body)
	if string(body) != `{"ok":true}` {
		t.Fatalf("unexpected body %q", body)
	}
}

func signedToken(t *testing.T, secret string, claims middleware.JWTClaims) string {
	t.Helper()
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	tokenStr, err := token.SignedString([]byte(secret))
	if err != nil {
		t.Fatal(err)
	}
	return tokenStr
}

func authenticatedRouter(routes []Route, secret string) http.Handler {
	return middleware.JWTAuth(middleware.JWTConfig{Secret: secret})(NewRouter(testRouterConfig(routes)))
}

func TestRouterForwardsUserIDFromJWTSubject(t *testing.T) {
	var gotUserID string
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotUserID = r.Header.Get("X-User-ID")
		w.WriteHeader(http.StatusOK)
	}))
	defer backend.Close()

	const secret = "test-secret"
	router := authenticatedRouter([]Route{{Prefix: "/api/v1/files", TargetURL: backend.URL}}, secret)

	token := signedToken(t, secret, middleware.JWTClaims{
		RegisteredClaims: jwt.RegisteredClaims{Subject: "user-from-sub"},
	})
	req := httptest.NewRequest(http.MethodGet, "/api/v1/files", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	if gotUserID != "user-from-sub" {
		t.Fatalf("backend received X-User-ID %q, want %q", gotUserID, "user-from-sub")
	}
}

func TestRouterForwardsUserIDFallbackToUserIDClaim(t *testing.T) {
	var gotUserID string
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotUserID = r.Header.Get("X-User-ID")
		w.WriteHeader(http.StatusOK)
	}))
	defer backend.Close()

	const secret = "test-secret"
	router := authenticatedRouter([]Route{{Prefix: "/api/v1/files", TargetURL: backend.URL}}, secret)

	token := signedToken(t, secret, middleware.JWTClaims{UserID: "user-from-custom-claim"})
	req := httptest.NewRequest(http.MethodGet, "/api/v1/files", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if gotUserID != "user-from-custom-claim" {
		t.Fatalf("backend received X-User-ID %q, want %q", gotUserID, "user-from-custom-claim")
	}
}

func TestRouterOmitsUserIDWithoutClaims(t *testing.T) {
	var hasHeader bool
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, hasHeader = r.Header["X-User-Id"]
		w.WriteHeader(http.StatusOK)
	}))
	defer backend.Close()

	router := NewRouter(testRouterConfig([]Route{{Prefix: "/api/v1/files", TargetURL: backend.URL}}))
	req := httptest.NewRequest(http.MethodGet, "/api/v1/files", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if hasHeader {
		t.Fatal("X-User-ID must not be set for unauthenticated requests")
	}
}

func TestRouterUnknownRouteReturnsJSON404(t *testing.T) {
	router := NewRouter(testRouterConfig(nil))
	req := httptest.NewRequest(http.MethodGet, "/api/v1/unknown", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", rec.Code)
	}
	if ct := rec.Header().Get("Content-Type"); ct != "application/json" {
		t.Fatalf("expected application/json, got %q", ct)
	}
	var body map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("body is not valid JSON: %v", err)
	}
	if body["error"] != "route not found" {
		t.Fatalf("unexpected error body %v", body)
	}
}

func TestRouterUnreachableBackendReturns502(t *testing.T) {
	// Reserve a port, then close it so the target is guaranteed unreachable.
	backend := httptest.NewServer(http.NotFoundHandler())
	target := backend.URL
	backend.Close()

	router := NewRouter(testRouterConfig([]Route{{Prefix: "/api/v1/files", TargetURL: target}}))
	req := httptest.NewRequest(http.MethodGet, "/api/v1/files", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadGateway {
		t.Fatalf("expected 502, got %d", rec.Code)
	}
	var body map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("body is not valid JSON: %v", err)
	}
	if body["error"] != "service unavailable" || body["target"] != "/api/v1/files" {
		t.Fatalf("unexpected error body %v", body)
	}
}

func TestRouterReturns503WhenCircuitBreakerOpens(t *testing.T) {
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer backend.Close()

	router := NewRouter(testRouterConfig([]Route{{Prefix: "/api/v1/files", TargetURL: backend.URL}}))

	// The breaker needs a minimum sample of 5 requests before it can trip.
	for i := 0; i < 5; i++ {
		req := httptest.NewRequest(http.MethodGet, "/api/v1/files", nil)
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, req)
		if rec.Code != http.StatusInternalServerError {
			t.Fatalf("request %d: expected 500 passthrough, got %d", i, rec.Code)
		}
	}

	req := httptest.NewRequest(http.MethodGet, "/api/v1/files", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503 once breaker opened, got %d", rec.Code)
	}
	var body map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("body is not valid JSON: %v", err)
	}
	if body["reason"] != "circuit breaker open" || body["service"] != "/api/v1/files" {
		t.Fatalf("unexpected error body %v", body)
	}
}
