package proxy

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func newTestRouter(t *testing.T, routes []Route) http.Handler {
	t.Helper()
	cbm := NewCircuitBreakerManager(CircuitBreakerConfig{
		MaxRequests:  5,
		Interval:     60,
		Timeout:      30,
		FailureRatio: 0.6,
	})
	cfg := RouterConfig{
		Routes:        routes,
		CBManager:     cbm,
		Logger:        zerolog.Nop(),
		EnableTracing: false,
	}
	return NewRouter(cfg)
}

func TestRouterNotFound(t *testing.T) {
	router := newTestRouter(t, []Route{})

	req := httptest.NewRequest("GET", "/nonexistent", nil)
	rr := httptest.NewRecorder()
	router.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusNotFound, rr.Code)

	var body map[string]string
	err := json.Unmarshal(rr.Body.Bytes(), &body)
	require.NoError(t, err)
	assert.Equal(t, "route not found", body["error"])
}

func TestRouterRoutesRegistered(t *testing.T) {
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{"status": "ok", "path": r.URL.Path})
	}))
	defer backend.Close()

	routes := []Route{
		{Prefix: "/api/v1/auth", TargetURL: backend.URL},
		{Prefix: "/api/v1/files", TargetURL: backend.URL},
	}
	router := newTestRouter(t, routes)

	req := httptest.NewRequest("GET", "/api/v1/auth/profile", nil)
	rr := httptest.NewRecorder()
	router.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)
}

func TestRouterProxyTargetResolution(t *testing.T) {
	var receivedPath string
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedPath = r.URL.Path
		w.WriteHeader(http.StatusOK)
	}))
	defer backend.Close()

	routes := []Route{
		{Prefix: "/api/v1/documents", TargetURL: backend.URL},
	}
	router := newTestRouter(t, routes)

	req := httptest.NewRequest("GET", "/api/v1/documents/abc-123", nil)
	rr := httptest.NewRecorder()
	router.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)
	assert.Contains(t, receivedPath, "/api/v1/documents")
}
