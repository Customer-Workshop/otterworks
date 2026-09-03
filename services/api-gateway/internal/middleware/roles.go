package middleware

import (
	"net/http"
	"strings"
)

// AdminRoles are the JWT role claims permitted to reach the admin API
// (auth-service issues ADMIN and OWNER; SUPER_ADMIN is the admin-service equivalent).
var AdminRoles = []string{"ADMIN", "SUPER_ADMIN", "OWNER"}

// AdminRoleExemptPaths are machine-to-machine admin endpoints that are
// authenticated by their own shared-secret header in admin-service rather than
// by a user JWT role.
var AdminRoleExemptPaths = []string{
	"/api/v1/admin/alerts/ingest",
	"/api/v1/admin/chaos",
}

// RequireRoles returns middleware that rejects requests under pathPrefix
// unless the validated JWT carries at least one of the allowed roles.
// Paths in exempt (exact or as a prefix segment) bypass the role check.
// It must run after JWTAuth; requests without claims are rejected.
func RequireRoles(pathPrefix string, allowed []string, exempt []string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			path := r.URL.Path
			if !matchesPrefix(path, pathPrefix) {
				next.ServeHTTP(w, r)
				return
			}
			for _, e := range exempt {
				if matchesPrefix(path, e) {
					next.ServeHTTP(w, r)
					return
				}
			}

			claims := GetJWTClaims(r.Context())
			if claims == nil || !hasAnyRole(claims.Roles, allowed) {
				writeJSONError(w, http.StatusForbidden, "insufficient role")
				return
			}

			next.ServeHTTP(w, r)
		})
	}
}

func matchesPrefix(path, prefix string) bool {
	return path == prefix || strings.HasPrefix(path, prefix+"/")
}

func hasAnyRole(have, allowed []string) bool {
	for _, h := range have {
		for _, a := range allowed {
			if strings.EqualFold(h, a) {
				return true
			}
		}
	}
	return false
}
