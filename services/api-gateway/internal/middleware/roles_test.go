package middleware

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestRequireRoles(t *testing.T) {
	handler := RequireRoles("/api/v1/admin", AdminRoles, AdminRoleExemptPaths)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	tests := []struct {
		name   string
		path   string
		claims *JWTClaims
		want   int
	}{
		{"admin role allowed", "/api/v1/admin/users", &JWTClaims{Roles: []string{"ADMIN", "USER"}}, http.StatusOK},
		{"lowercase admin role allowed", "/api/v1/admin/users", &JWTClaims{Roles: []string{"admin"}}, http.StatusOK},
		{"owner role allowed", "/api/v1/admin/users", &JWTClaims{Roles: []string{"OWNER"}}, http.StatusOK},
		{"alerts ingest exempt", "/api/v1/admin/alerts/ingest", nil, http.StatusOK},
		{"chaos exempt", "/api/v1/admin/chaos", &JWTClaims{Roles: []string{"USER"}}, http.StatusOK},
		{"exempt prefix must match segment", "/api/v1/admin/chaos-config", &JWTClaims{Roles: []string{"USER"}}, http.StatusForbidden},
		{"user role forbidden", "/api/v1/admin/users", &JWTClaims{Roles: []string{"USER"}}, http.StatusForbidden},
		{"no roles forbidden", "/api/v1/admin/users", &JWTClaims{}, http.StatusForbidden},
		{"no claims forbidden", "/api/v1/admin", nil, http.StatusForbidden},
		{"non-admin path unaffected", "/api/v1/files", &JWTClaims{Roles: []string{"USER"}}, http.StatusOK},
		{"prefix must match segment", "/api/v1/administrators", &JWTClaims{Roles: []string{"USER"}}, http.StatusOK},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, tt.path, nil)
			if tt.claims != nil {
				req = req.WithContext(context.WithValue(req.Context(), jwtClaimsKey{}, tt.claims))
			}
			rec := httptest.NewRecorder()
			handler.ServeHTTP(rec, req)
			assert.Equal(t, tt.want, rec.Code)
		})
	}
}
