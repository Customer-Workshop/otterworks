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

func routerTestCBConfig() CircuitBreakerConfig {
	return CircuitBreakerConfig{
		MaxRequests:  2,
		Interval:     60 * time.Second,
		Timeout:      10 * time.Second,
		FailureRatio: 0.5,
	}
}

func TestNewRouter_NotFound(t *testing.T) {
	logger := zerolog.Nop()
	cbm := NewCircuitBreakerManager(routerTestCBConfig())

	router := NewRouter(RouterConfig{
		Routes:    []Route{},
		CBManager: cbm,
		Logger:    logger,
	})

	req := httptest.NewRequest(http.MethodGet, "/nonexistent", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusNotFound, rec.Code)

	var body map[string]string
	err := json.NewDecoder(rec.Body).Decode(&body)
	require.NoError(t, err)
	assert.Equal(t, "route not found", body["error"])
}

func TestNewRouter_ProxiesToBackend(t *testing.T) {
	// Set up a mock backend service
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{
			"message": "hello from backend",
			"path":    r.URL.Path,
		})
	}))
	defer backend.Close()

	logger := zerolog.Nop()
	cbm := NewCircuitBreakerManager(routerTestCBConfig())

	router := NewRouter(RouterConfig{
		Routes: []Route{
			{Prefix: "/api/v1/test", TargetURL: backend.URL},
		},
		CBManager:     cbm,
		Logger:        logger,
		EnableTracing: false,
	})

	req := httptest.NewRequest(http.MethodGet, "/api/v1/test/items", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code)

	var body map[string]string
	err := json.NewDecoder(rec.Body).Decode(&body)
	require.NoError(t, err)
	assert.Equal(t, "hello from backend", body["message"])
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

	logger := zerolog.Nop()
	cbm := NewCircuitBreakerManager(routerTestCBConfig())

	router := NewRouter(RouterConfig{
		Routes: []Route{
			{Prefix: "/api/v1/auth", TargetURL: backend1.URL},
			{Prefix: "/api/v1/files", TargetURL: backend2.URL},
		},
		CBManager: cbm,
		Logger:    logger,
	})

	// Test route to auth service
	req1 := httptest.NewRequest(http.MethodGet, "/api/v1/auth/me", nil)
	rec1 := httptest.NewRecorder()
	router.ServeHTTP(rec1, req1)

	var body1 map[string]string
	json.NewDecoder(rec1.Body).Decode(&body1)
	assert.Equal(t, "auth", body1["service"])

	// Test route to files service
	req2 := httptest.NewRequest(http.MethodGet, "/api/v1/files/list", nil)
	rec2 := httptest.NewRecorder()
	router.ServeHTTP(rec2, req2)

	var body2 map[string]string
	json.NewDecoder(rec2.Body).Decode(&body2)
	assert.Equal(t, "files", body2["service"])
}

func TestNewRouter_ReturnsNotFoundForUnmatchedPaths(t *testing.T) {
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer backend.Close()

	logger := zerolog.Nop()
	cbm := NewCircuitBreakerManager(routerTestCBConfig())

	router := NewRouter(RouterConfig{
		Routes: []Route{
			{Prefix: "/api/v1/files", TargetURL: backend.URL},
		},
		CBManager: cbm,
		Logger:    logger,
	})

	req := httptest.NewRequest(http.MethodGet, "/api/v1/unknown/endpoint", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusNotFound, rec.Code)
}

func TestNewRouter_HandlesBackendError(t *testing.T) {
	// Use an unreachable backend URL
	logger := zerolog.Nop()
	cbm := NewCircuitBreakerManager(routerTestCBConfig())

	router := NewRouter(RouterConfig{
		Routes: []Route{
			{Prefix: "/api/v1/broken", TargetURL: "http://127.0.0.1:1"},
		},
		CBManager: cbm,
		Logger:    logger,
	})

	req := httptest.NewRequest(http.MethodGet, "/api/v1/broken/test", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	// Should either be 502 (proxy error) or 503 (circuit breaker open)
	assert.True(t, rec.Code == http.StatusBadGateway || rec.Code == http.StatusServiceUnavailable)
}

func TestNewRouter_ContentTypeJSON(t *testing.T) {
	logger := zerolog.Nop()
	cbm := NewCircuitBreakerManager(routerTestCBConfig())

	router := NewRouter(RouterConfig{
		Routes:    []Route{},
		CBManager: cbm,
		Logger:    logger,
	})

	req := httptest.NewRequest(http.MethodGet, "/any/path", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	assert.Equal(t, "application/json", rec.Header().Get("Content-Type"))
}
