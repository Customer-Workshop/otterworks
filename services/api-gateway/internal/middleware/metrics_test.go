package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestNormalizePath_Auth(t *testing.T) {
	assert.Equal(t, "/api/v1/auth", normalizePath("/api/v1/auth/login"))
	assert.Equal(t, "/api/v1/auth", normalizePath("/api/v1/auth/register"))
	assert.Equal(t, "/api/v1/auth", normalizePath("/api/v1/auth"))
}

func TestNormalizePath_Files(t *testing.T) {
	assert.Equal(t, "/api/v1/files", normalizePath("/api/v1/files"))
	assert.Equal(t, "/api/v1/files", normalizePath("/api/v1/files/upload"))
	assert.Equal(t, "/api/v1/files", normalizePath("/api/v1/files/some-uuid/download"))
}

func TestNormalizePath_Documents(t *testing.T) {
	assert.Equal(t, "/api/v1/documents", normalizePath("/api/v1/documents"))
	assert.Equal(t, "/api/v1/documents", normalizePath("/api/v1/documents/abc-123"))
}

func TestNormalizePath_Collab(t *testing.T) {
	assert.Equal(t, "/api/v1/collab", normalizePath("/api/v1/collab/join"))
}

func TestNormalizePath_Notifications(t *testing.T) {
	assert.Equal(t, "/api/v1/notifications", normalizePath("/api/v1/notifications/unread"))
}

func TestNormalizePath_Search(t *testing.T) {
	assert.Equal(t, "/api/v1/search", normalizePath("/api/v1/search?q=hello"))
}

func TestNormalizePath_Analytics(t *testing.T) {
	assert.Equal(t, "/api/v1/analytics", normalizePath("/api/v1/analytics/events"))
}

func TestNormalizePath_Admin(t *testing.T) {
	assert.Equal(t, "/api/v1/admin", normalizePath("/api/v1/admin/users"))
}

func TestNormalizePath_Audit(t *testing.T) {
	assert.Equal(t, "/api/v1/audit", normalizePath("/api/v1/audit/events"))
}

func TestNormalizePath_Unknown(t *testing.T) {
	assert.Equal(t, "other", normalizePath("/"))
	assert.Equal(t, "other", normalizePath("/health"))
	assert.Equal(t, "other", normalizePath("/random/path"))
}

func TestMetrics_MiddlewareCallsNext(t *testing.T) {
	called := false
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		w.WriteHeader(http.StatusOK)
	})

	handler := Metrics(next)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/auth/login", nil)
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	assert.True(t, called)
	assert.Equal(t, http.StatusOK, rec.Code)
}

func TestMetrics_RecordsDifferentStatusCodes(t *testing.T) {
	tests := []struct {
		name   string
		status int
	}{
		{"2xx", http.StatusOK},
		{"4xx", http.StatusNotFound},
		{"5xx", http.StatusInternalServerError},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			handler := Metrics(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(tc.status)
			}))

			req := httptest.NewRequest(http.MethodGet, "/api/v1/files/test", nil)
			rec := httptest.NewRecorder()
			handler.ServeHTTP(rec, req)

			assert.Equal(t, tc.status, rec.Code)
		})
	}
}
