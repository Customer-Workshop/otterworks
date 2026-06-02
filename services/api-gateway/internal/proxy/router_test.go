package proxy

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func testCBConfig() CircuitBreakerConfig {
	return CircuitBreakerConfig{
		MaxRequests:  2,
		Interval:     60 * time.Second,
		Timeout:      10 * time.Second,
		FailureRatio: 0.5,
	}
}

func TestNewRouter_NotFoundHandler(t *testing.T) {
	cfg := RouterConfig{
		Routes:    []Route{},
		CBManager: NewCircuitBreakerManager(testCBConfig()),
		Logger:    zerolog.Nop(),
	}

	router := NewRouter(cfg)

	req := httptest.NewRequest(http.MethodGet, "/nonexistent", nil)
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusNotFound, rec.Code)
	assert.Contains(t, rec.Header().Get("Content-Type"), "application/json")

	var body map[string]string
	err := json.NewDecoder(rec.Body).Decode(&body)
	require.NoError(t, err)
	assert.Equal(t, "route not found", body["error"])
}

func TestNewRouter_ProxiesToBackend(t *testing.T) {
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{
			"proxied_path": r.URL.Path,
		})
	}))
	defer backend.Close()

	cfg := RouterConfig{
		Routes: []Route{
			{Prefix: "/api/v1/test", TargetURL: backend.URL},
		},
		CBManager:     NewCircuitBreakerManager(testCBConfig()),
		Logger:        zerolog.Nop(),
		EnableTracing: false,
	}

	router := NewRouter(cfg)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/test/hello", nil)
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code)

	var body map[string]string
	err := json.NewDecoder(rec.Body).Decode(&body)
	require.NoError(t, err)
	assert.Contains(t, body["proxied_path"], "/api/v1/test/hello")
}

func TestNewRouter_ProxyErrorReturns502(t *testing.T) {
	// Use an address that will refuse connections
	cfg := RouterConfig{
		Routes: []Route{
			{Prefix: "/api/v1/bad", TargetURL: "http://127.0.0.1:1"},
		},
		CBManager:     NewCircuitBreakerManager(testCBConfig()),
		Logger:        zerolog.Nop(),
		EnableTracing: false,
	}

	router := NewRouter(cfg)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/bad/test", nil)
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	// Either circuit breaker 503 or proxy error 502 are acceptable
	assert.True(t, rec.Code == http.StatusBadGateway || rec.Code == http.StatusServiceUnavailable,
		"expected 502 or 503, got %d", rec.Code)
}

func TestNewRouter_MultipleRoutes(t *testing.T) {
	backend1 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]string{"service": "auth"})
	}))
	defer backend1.Close()

	backend2 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]string{"service": "files"})
	}))
	defer backend2.Close()

	cfg := RouterConfig{
		Routes: []Route{
			{Prefix: "/api/v1/auth", TargetURL: backend1.URL},
			{Prefix: "/api/v1/files", TargetURL: backend2.URL},
		},
		CBManager:     NewCircuitBreakerManager(testCBConfig()),
		Logger:        zerolog.Nop(),
		EnableTracing: false,
	}

	router := NewRouter(cfg)

	// Test auth route
	req1 := httptest.NewRequest(http.MethodGet, "/api/v1/auth/login", nil)
	rec1 := httptest.NewRecorder()
	router.ServeHTTP(rec1, req1)
	assert.Equal(t, http.StatusOK, rec1.Code)

	var body1 map[string]string
	json.NewDecoder(rec1.Body).Decode(&body1)
	assert.Equal(t, "auth", body1["service"])

	// Test files route
	req2 := httptest.NewRequest(http.MethodGet, "/api/v1/files/list", nil)
	rec2 := httptest.NewRecorder()
	router.ServeHTTP(rec2, req2)
	assert.Equal(t, http.StatusOK, rec2.Code)

	var body2 map[string]string
	json.NewDecoder(rec2.Body).Decode(&body2)
	assert.Equal(t, "files", body2["service"])
}
