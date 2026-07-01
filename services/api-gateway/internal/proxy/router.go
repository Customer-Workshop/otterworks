package proxy

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httputil"
	"net/url"

	"github.com/go-chi/chi/v5"
	"github.com/rs/zerolog"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"

	"github.com/Cognition-Partner-Workshops/otterworks/services/api-gateway/internal/middleware"
)

// Headers used to convey the gateway-authenticated user identity to backend
// services. The signature lets backends verify the identity was injected by
// the gateway (which holds the shared secret) rather than spoofed by a client.
const (
	userIDHeader          = "X-User-ID"
	userIDSignatureHeader = "X-User-ID-Signature"
)

// signUserID returns the hex-encoded HMAC-SHA256 of the user ID using the
// shared secret, matching the verification performed by backend services.
func signUserID(secret, userID string) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(userID))
	return hex.EncodeToString(mac.Sum(nil))
}

// Route defines a mapping from a URL prefix to a backend service.
type Route struct {
	Prefix    string
	TargetURL string
}

// RouterConfig holds configuration for the reverse proxy router.
type RouterConfig struct {
	Routes        []Route
	CBManager     *CircuitBreakerManager
	Logger        zerolog.Logger
	EnableTracing bool
	// IdentitySigningSecret is the shared secret used to sign the
	// gateway-injected X-User-ID header so backend services can verify its
	// provenance. When empty, no signature is attached.
	IdentitySigningSecret string
}

// NewRouter creates a chi router with all service routes mounted.
func NewRouter(cfg RouterConfig) chi.Router {
	r := chi.NewRouter()

	for _, route := range cfg.Routes {
		route := route // capture loop var
		r.Route(route.Prefix, func(sub chi.Router) {
			handler := newProxyHandler(route, cfg)
			sub.HandleFunc("/*", handler)
			sub.HandleFunc("/", handler)
		})
	}
	r.NotFound(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusNotFound)
		json.NewEncoder(w).Encode(map[string]string{
			"error": "route not found",
		})
	})

	return r
}

func newProxyHandler(route Route, cfg RouterConfig) http.HandlerFunc {
	// The full request path (e.g. /api/v1/auth/register) is preserved in
	// req.URL.Path, so the target URL should be just the backend host.
	// httputil.ReverseProxy joins the target path with req.URL.Path.
	target, err := url.Parse(route.TargetURL)
	if err != nil {
		cfg.Logger.Fatal().Err(err).Str("target", route.TargetURL).Msg("invalid proxy target URL")
	}

	proxy := httputil.NewSingleHostReverseProxy(target)

	// Wrap the default director to forward authenticated user identity.
	// The auth-service issues JWTs with the user ID in the standard "sub" claim
	// (claims.Subject). Fall back to the custom "user_id" claim for compatibility.
	signingSecret := cfg.IdentitySigningSecret
	defaultDirector := proxy.Director
	proxy.Director = func(req *http.Request) {
		defaultDirector(req)
		// Never trust client-supplied identity headers: strip them before
		// deriving identity from the validated JWT so a spoofed X-User-ID
		// can never reach a backend service.
		req.Header.Del(userIDHeader)
		req.Header.Del(userIDSignatureHeader)
		if claims := middleware.GetJWTClaims(req.Context()); claims != nil {
			userID := claims.Subject
			if userID == "" {
				userID = claims.UserID
			}
			if userID != "" {
				req.Header.Set(userIDHeader, userID)
				if signingSecret != "" {
					req.Header.Set(userIDSignatureHeader, signUserID(signingSecret, userID))
				}
			}
		}
	}

	proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		cfg.Logger.Error().
			Err(err).
			Str("target", route.TargetURL).
			Str("path", r.URL.Path).
			Str("method", r.Method).
			Msg("proxy error")

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadGateway)
		json.NewEncoder(w).Encode(map[string]string{
			"error":  "service unavailable",
			"target": route.Prefix,
		})
	}

	var handler http.Handler = proxy
	if cfg.EnableTracing {
		handler = otelhttp.NewHandler(proxy, "proxy:"+route.Prefix)
	}

	cb := cfg.CBManager.Get(route.Prefix)

	return func(w http.ResponseWriter, r *http.Request) {
		if err := cb.Execute(handler, w, r); err != nil {
			cfg.Logger.Warn().
				Str("circuit_breaker", route.Prefix).
				Str("state", cb.State().String()).
				Msg("circuit breaker rejected request")

			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusServiceUnavailable)
			json.NewEncoder(w).Encode(map[string]string{
				"error":   "service temporarily unavailable",
				"service": route.Prefix,
				"reason":  "circuit breaker open",
			})
		}
	}
}
