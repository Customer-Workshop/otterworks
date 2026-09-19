package proxy

import (
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Cognition-Partner-Workshops/otterworks/services/api-gateway/internal/middleware"
	"github.com/golang-jwt/jwt/v5"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestRouterForwardsIdentityClaimsAndStripsSpoofedHeaders(t *testing.T) {
	const secret = "router-test-secret"
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "user-123", r.Header.Get("X-User-ID"))
		assert.Equal(t, "user@example.com", r.Header.Get("X-User-Email"))
		assert.Equal(t, "ADMIN,USER", r.Header.Get("X-User-Roles"))
		w.WriteHeader(http.StatusNoContent)
	}))
	defer backend.Close()

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, middleware.JWTClaims{
		Email: "user@example.com",
		Roles: []string{"ADMIN", "USER"},
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   "user-123",
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
		},
	})
	tokenString, err := token.SignedString([]byte(secret))
	require.NoError(t, err)

	router := NewRouter(RouterConfig{
		Routes: []Route{{Prefix: "/api/v1/billing", TargetURL: backend.URL}},
		CBManager: NewCircuitBreakerManager(CircuitBreakerConfig{
			MaxRequests: 2, Interval: time.Minute, Timeout: time.Second, FailureRatio: 0.5,
		}),
		Logger: zerolog.Nop(),
	})
	handler := middleware.JWTAuth(middleware.JWTConfig{
		Secret: secret,
		ProtectedPrefixPath: []string{"/api/v1/billing"},
	})(router)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/billing/me", nil)
	req.Header.Set("Authorization", "Bearer "+tokenString)
	req.Header.Set("X-User-ID", "attacker")
	req.Header.Set("X-User-Email", "attacker@example.com")
	req.Header.Set("X-User-Roles", "ADMIN")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusNoContent, rec.Code)
}

func TestRouterStripsSpoofedRolesWhenTokenHasNoRoles(t *testing.T) {
	const secret = "router-test-secret"
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assert.Empty(t, r.Header.Get("X-User-Roles"))
		_, _ = io.WriteString(w, "ok")
	}))
	defer backend.Close()

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, middleware.JWTClaims{
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   "user-123",
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
		},
	})
	tokenString, err := token.SignedString([]byte(secret))
	require.NoError(t, err)

	router := NewRouter(RouterConfig{
		Routes: []Route{{Prefix: "/api/v1/billing", TargetURL: backend.URL}},
		CBManager: NewCircuitBreakerManager(CircuitBreakerConfig{
			MaxRequests: 2, Interval: time.Minute, Timeout: time.Second, FailureRatio: 0.5,
		}),
		Logger: zerolog.Nop(),
	})
	handler := middleware.JWTAuth(middleware.JWTConfig{
		Secret: secret,
		ProtectedPrefixPath: []string{"/api/v1/billing"},
	})(router)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/billing/me", nil)
	req.Header.Set("Authorization", "Bearer "+tokenString)
	req.Header.Set("X-User-Roles", "ADMIN")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code)
}
