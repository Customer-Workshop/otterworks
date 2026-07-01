package proxy

import (
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/golang-jwt/jwt/v5"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/Cognition-Partner-Workshops/otterworks/services/api-gateway/internal/middleware"
)

const testSigningSecret = "test-shared-secret"

func newTestCBManager() *CircuitBreakerManager {
	return NewCircuitBreakerManager(CircuitBreakerConfig{
		MaxRequests:  5,
		Interval:     60 * time.Second,
		Timeout:      10 * time.Second,
		FailureRatio: 0.6,
	})
}

// captureBackend returns an httptest server that records the headers of the
// last request it received.
func captureBackend(t *testing.T, received *http.Header) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		*received = r.Header.Clone()
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)
	return srv
}

func TestSignUserID_DeterministicAndSecretDependent(t *testing.T) {
	a := signUserID(testSigningSecret, "user-1")
	b := signUserID(testSigningSecret, "user-1")
	assert.Equal(t, a, b, "same secret+user must produce same signature")

	assert.NotEqual(t, a, signUserID("other-secret", "user-1"))
	assert.NotEqual(t, a, signUserID(testSigningSecret, "user-2"))
}

// A request without validated JWT claims must have any client-supplied
// X-User-ID (and signature) stripped before reaching the backend.
func TestDirector_StripsSpoofedHeaderWithoutClaims(t *testing.T) {
	var received http.Header
	backend := captureBackend(t, &received)

	router := NewRouter(RouterConfig{
		Routes:                []Route{{Prefix: "/api/v1/search", TargetURL: backend.URL}},
		CBManager:             newTestCBManager(),
		Logger:                zerolog.New(io.Discard),
		IdentitySigningSecret: testSigningSecret,
	})

	req := httptest.NewRequest(http.MethodGet, "/api/v1/search/?q=x", nil)
	req.Header.Set("X-User-ID", "victim-user")
	req.Header.Set("X-User-ID-Signature", "forged")
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	require.Equal(t, http.StatusOK, rec.Code)
	assert.Empty(t, received.Get("X-User-ID"), "spoofed X-User-ID must be stripped")
	assert.Empty(t, received.Get("X-User-ID-Signature"), "spoofed signature must be stripped")
}

// With valid JWT claims, the gateway must overwrite any client-supplied
// X-User-ID with the JWT identity and attach a valid HMAC signature.
func TestDirector_SignsIdentityFromClaimsAndStripsSpoof(t *testing.T) {
	var received http.Header
	backend := captureBackend(t, &received)

	proxyRouter := NewRouter(RouterConfig{
		Routes:                []Route{{Prefix: "/api/v1/search", TargetURL: backend.URL}},
		CBManager:             newTestCBManager(),
		Logger:                zerolog.New(io.Discard),
		IdentitySigningSecret: testSigningSecret,
	})

	r := chi.NewRouter()
	r.Use(middleware.JWTAuth(middleware.JWTConfig{
		Secret:              testSigningSecret,
		ProtectedPrefixPath: []string{"/api/v1/search"},
	}))
	r.Mount("/", proxyRouter)

	claims := &middleware.JWTClaims{
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   "real-user",
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
		},
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	signed, err := token.SignedString([]byte(testSigningSecret))
	require.NoError(t, err)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/search/?q=x", nil)
	req.Header.Set("Authorization", "Bearer "+signed)
	req.Header.Set("X-User-ID", "attacker-spoof")
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	require.Equal(t, http.StatusOK, rec.Code)
	assert.Equal(t, "real-user", received.Get("X-User-ID"), "identity must come from JWT, not the client header")
	assert.Equal(t, signUserID(testSigningSecret, "real-user"), received.Get("X-User-ID-Signature"))
}
