package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestMetricsMiddleware(t *testing.T) {
	handler := Metrics(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("ok"))
	}))

	req := httptest.NewRequest("GET", "/api/v1/auth/login", nil)
	rr := httptest.NewRecorder()

	handler.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)
	assert.Equal(t, "ok", rr.Body.String())
}

func TestNormalizePath(t *testing.T) {
	tests := []struct {
		path     string
		expected string
	}{
		{"/api/v1/auth/login", "/api/v1/auth"},
		{"/api/v1/auth/register", "/api/v1/auth"},
		{"/api/v1/files/123", "/api/v1/files"},
		{"/api/v1/documents/abc/versions", "/api/v1/documents"},
		{"/api/v1/collab/room", "/api/v1/collab"},
		{"/api/v1/notifications", "/api/v1/notifications"},
		{"/api/v1/search?q=test", "/api/v1/search"},
		{"/api/v1/analytics/events", "/api/v1/analytics"},
		{"/api/v1/admin/users", "/api/v1/admin"},
		{"/api/v1/audit/events", "/api/v1/audit"},
		{"/health", "other"},
		{"/random/path", "other"},
	}

	for _, tt := range tests {
		t.Run(tt.path, func(t *testing.T) {
			assert.Equal(t, tt.expected, normalizePath(tt.path))
		})
	}
}
