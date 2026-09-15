package middleware

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestNormalizePath(t *testing.T) {
	tests := []struct {
		name string
		path string
		want string
	}{
		{"auth exact", "/api/v1/auth", "/api/v1/auth"},
		{"auth nested", "/api/v1/auth/login", "/api/v1/auth"},
		{"files with id", "/api/v1/files/123e4567-e89b-12d3-a456-426614174000", "/api/v1/files"},
		{"documents", "/api/v1/documents/42/versions", "/api/v1/documents"},
		{"collab", "/api/v1/collab/session/abc", "/api/v1/collab"},
		{"notifications", "/api/v1/notifications/unread", "/api/v1/notifications"},
		{"search", "/api/v1/search?q=otter", "/api/v1/search"},
		{"analytics", "/api/v1/analytics/reports/7", "/api/v1/analytics"},
		{"admin", "/api/v1/admin/users", "/api/v1/admin"},
		{"audit", "/api/v1/audit/events", "/api/v1/audit"},
		{"unknown api route", "/api/v1/unknown", "other"},
		{"health", "/health", "other"},
		{"root", "/", "other"},
		{"empty", "", "other"},
		{"prefix shorter than route", "/api/v1/aut", "other"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			assert.Equal(t, tt.want, normalizePath(tt.path))
		})
	}
}
