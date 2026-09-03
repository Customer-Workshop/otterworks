package middleware

import (
	"net/http"
	"strings"
)

// AdminRoles are the JWT role claims permitted to reach the admin API.
var AdminRoles = []string{"ADMIN", "SUPER_ADMIN"}

// RequireRoles returns middleware that rejects requests under pathPrefix
// unless the validated JWT carries at least one of the allowed roles.
// It must run after JWTAuth; requests without claims are rejected.
func RequireRoles(pathPrefix string, allowed []string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			path := r.URL.Path
			if path != pathPrefix && !strings.HasPrefix(path, pathPrefix+"/") {
				next.ServeHTTP(w, r)
				return
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
