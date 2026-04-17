package middleware

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

type jwtClaimsKey struct{}

// JWTClaims represents the claims extracted from a validated JWT.
type JWTClaims struct {
	UserID string
	Email  string
	Roles  []string
	jwt.RegisteredClaims
}

// JWTConfig holds configuration for JWT validation middleware.
type JWTConfig struct {
	Secret     string
	PublicPath []string // paths that skip JWT validation
}

// DefaultPublicPaths returns the default set of paths that skip JWT validation.
func DefaultPublicPaths() []string {
	return []string{
		"/health",
		"/metrics",
		"/api/v1/auth/login",
		"/api/v1/auth/register",
	}
}

// JWTAuth returns middleware that validates JWT tokens on protected routes.
func JWTAuth(cfg JWTConfig) func(http.Handler) http.Handler {
	publicPaths := make(map[string]bool, len(cfg.PublicPath))
	for _, p := range cfg.PublicPath {
		publicPaths[p] = true
	}

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Skip JWT validation for public paths
			if isPublicPath(r.URL.Path, publicPaths) {
				next.ServeHTTP(w, r)
				return
			}

			tokenStr := extractBearerToken(r)
			if tokenStr == "" {
				writeJSONError(w, http.StatusUnauthorized, "missing or invalid authorization header")
				return
			}

			claims, err := validateToken(tokenStr, cfg.Secret)
			if err != nil {
				writeJSONError(w, http.StatusUnauthorized, fmt.Sprintf("invalid token: %v", err))
				return
			}

			ctx := context.WithValue(r.Context(), jwtClaimsKey{}, claims)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// GetJWTClaims retrieves JWT claims from the request context.
func GetJWTClaims(ctx context.Context) *JWTClaims {
	if claims, ok := ctx.Value(jwtClaimsKey{}).(*JWTClaims); ok {
		return claims
	}
	return nil
}

func extractBearerToken(r *http.Request) string {
	auth := r.Header.Get("Authorization")
	if auth == "" {
		return ""
	}
	parts := strings.SplitN(auth, " ", 2)
	if len(parts) != 2 || !strings.EqualFold(parts[0], "bearer") {
		return ""
	}
	return parts[1]
}

func validateToken(tokenStr, secret string) (*JWTClaims, error) {
	claims := &JWTClaims{}
	token, err := jwt.ParseWithClaims(tokenStr, claims, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
		}
		return []byte(secret), nil
	})
	if err != nil {
		return nil, err
	}
	if !token.Valid {
		return nil, fmt.Errorf("token is not valid")
	}

	// Check expiration
	if claims.ExpiresAt != nil && claims.ExpiresAt.Time.Before(time.Now()) {
		return nil, fmt.Errorf("token has expired")
	}

	return claims, nil
}

func isPublicPath(path string, publicPaths map[string]bool) bool {
	if publicPaths[path] {
		return true
	}
	// Check prefix matches for paths like /health, /metrics
	for p := range publicPaths {
		if strings.HasPrefix(path, p+"/") || path == p {
			return true
		}
	}
	return false
}

func writeJSONError(w http.ResponseWriter, status int, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(map[string]string{
		"error": message,
	})
}
