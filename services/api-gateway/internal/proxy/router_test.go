package proxy

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
)

func newTestRouter(t *testing.T) http.Handler {
	t.Helper()
	return NewRouter(RouterConfig{
		Routes:    []Route{{Prefix: "/api/v1/down", TargetURL: "http://127.0.0.1:1"}},
		CBManager: NewCircuitBreakerManager(defaultTestConfig()),
		Logger:    zerolog.Nop(),
	})
}

func TestRouter_NotFoundRespondsWithJSON(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/does/not/exist", nil)
	rec := httptest.NewRecorder()

	newTestRouter(t).ServeHTTP(rec, req)

	assert.Equal(t, http.StatusNotFound, rec.Code)
	assert.Equal(t, contentTypeJSON, rec.Header().Get("Content-Type"))
	assert.JSONEq(t, `{"error":"route not found"}`, rec.Body.String())
}

func TestRouter_ProxyErrorRespondsWithJSON(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/api/v1/down/ping", nil)
	rec := httptest.NewRecorder()

	newTestRouter(t).ServeHTTP(rec, req)

	assert.Equal(t, http.StatusBadGateway, rec.Code)
	assert.Equal(t, contentTypeJSON, rec.Header().Get("Content-Type"))
	assert.JSONEq(t, `{"error":"service unavailable","target":"/api/v1/down"}`, rec.Body.String())
}
