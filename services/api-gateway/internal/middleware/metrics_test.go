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

func TestMetrics_HandlesMultipleStatusCodes(t *testing.T) {
	tests := []struct {
		name   string
		status int
	}{
		{"200 OK", http.StatusOK},
		{"201 Created", http.StatusCreated},
		{"400 Bad Request", http.StatusBadRequest},
		{"404 Not Found", http.StatusNotFound},
		{"500 Internal Error", http.StatusInternalServerError},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			handler := Metrics(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(tt.status)
			}))

			req := httptest.NewRequest(http.MethodGet, "/api/v1/auth/login", nil)
			rec := httptest.NewRecorder()
			handler.ServeHTTP(rec, req)

			assert.Equal(t, tt.status, rec.Code)
		})
	}
}

func TestNormalizePath(t *testing.T) {
	tests := []struct {
		name string
		path string
		want string
	}{
		{"auth prefix", "/api/v1/auth/login", "/api/v1/auth"},
		{"auth register", "/api/v1/auth/register", "/api/v1/auth"},
		{"files prefix", "/api/v1/files/abc-123", "/api/v1/files"},
		{"files root", "/api/v1/files", "/api/v1/files"},
		{"documents prefix", "/api/v1/documents/doc-1/versions", "/api/v1/documents"},
		{"collab prefix", "/api/v1/collab/rooms", "/api/v1/collab"},
		{"notifications prefix", "/api/v1/notifications/user-1", "/api/v1/notifications"},
		{"search prefix", "/api/v1/search?q=hello", "/api/v1/search"},
		{"analytics prefix", "/api/v1/analytics/dashboard", "/api/v1/analytics"},
		{"admin prefix", "/api/v1/admin/users", "/api/v1/admin"},
		{"audit prefix", "/api/v1/audit/events", "/api/v1/audit"},
		{"unknown path", "/some/random/path", "other"},
		{"root path", "/", "other"},
		{"empty path", "", "other"},
		{"health path", "/health", "other"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := normalizePath(tt.path)
			assert.Equal(t, tt.want, got)
		})
	}
}
