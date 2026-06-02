package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestMetrics_RecordsRequest(t *testing.T) {
	handler := Metrics(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodGet, "/api/v1/files/123", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code)
}

func TestNormalizePath_KnownPrefixes(t *testing.T) {
	tests := []struct {
		input    string
		expected string
	}{
		{"/api/v1/auth/login", "/api/v1/auth"},
		{"/api/v1/auth", "/api/v1/auth"},
		{"/api/v1/files/123/download", "/api/v1/files"},
		{"/api/v1/documents/abc", "/api/v1/documents"},
		{"/api/v1/collab/session", "/api/v1/collab"},
		{"/api/v1/notifications/1", "/api/v1/notifications"},
		{"/api/v1/search?q=test", "/api/v1/search"},
		{"/api/v1/analytics/events", "/api/v1/analytics"},
		{"/api/v1/admin/users", "/api/v1/admin"},
		{"/api/v1/audit/logs", "/api/v1/audit"},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			result := normalizePath(tt.input)
			assert.Equal(t, tt.expected, result)
		})
	}
}

func TestNormalizePath_UnknownPath(t *testing.T) {
	assert.Equal(t, "other", normalizePath("/unknown"))
	assert.Equal(t, "other", normalizePath("/"))
	assert.Equal(t, "other", normalizePath("/health"))
	assert.Equal(t, "other", normalizePath("/metrics"))
}

func TestNormalizePath_ShortPaths(t *testing.T) {
	assert.Equal(t, "other", normalizePath(""))
	assert.Equal(t, "other", normalizePath("/a"))
	assert.Equal(t, "other", normalizePath("/api"))
}
