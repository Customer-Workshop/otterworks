package middleware

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestNormalizePath_CollapsesToRoutePrefix(t *testing.T) {
	tests := []struct {
		path string
		want string
	}{
		{"/api/v1/auth/login", "/api/v1/auth"},
		{"/api/v1/files/123/download", "/api/v1/files"},
		{"/api/v1/documents", "/api/v1/documents"},
		{"/api/v1/documents/abc-123/versions", "/api/v1/documents"},
		{"/api/v1/collab/rooms/1", "/api/v1/collab"},
		{"/api/v1/notifications/unread", "/api/v1/notifications"},
		{"/api/v1/search?q=x", "/api/v1/search"},
		{"/api/v1/analytics/events", "/api/v1/analytics"},
		{"/api/v1/admin/users", "/api/v1/admin"},
		{"/api/v1/audit/logs", "/api/v1/audit"},
	}

	for _, tt := range tests {
		t.Run(tt.path, func(t *testing.T) {
			assert.Equal(t, tt.want, normalizePath(tt.path))
		})
	}
}

func TestNormalizePath_UnknownIsOther(t *testing.T) {
	for _, path := range []string{"/", "/health", "/api/v1/unknown", "/api/v1/doc", ""} {
		assert.Equal(t, "other", normalizePath(path), path)
	}
}

func TestMetricsPathPrefixes_AreUnique(t *testing.T) {
	seen := make(map[string]struct{}, len(metricsPathPrefixes))
	for _, prefix := range metricsPathPrefixes {
		_, dup := seen[prefix]
		assert.False(t, dup, "duplicate prefix %q", prefix)
		seen[prefix] = struct{}{}
	}
}
