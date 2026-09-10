package middleware

import (
	"net/http"
	"strconv"
	"strings"
)

// CORSConfig holds configuration for CORS middleware.
type CORSConfig struct {
	AllowedOrigins   []string
	AllowedMethods   []string
	AllowedHeaders   []string
	ExposedHeaders   []string
	AllowCredentials bool
	MaxAge           int
}

// DefaultCORSConfig returns a default CORS configuration.
// https://localhost and capacitor://localhost are the WebView origins of the
// Capacitor mobile app (Android and iOS respectively).
func DefaultCORSConfig() CORSConfig {
	return CORSConfig{
		AllowedOrigins:   []string{"http://localhost:3000", "http://localhost:4200", "https://localhost", "capacitor://localhost"},
		AllowedMethods:   []string{"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"},
		AllowedHeaders:   []string{"Accept", "Authorization", "Content-Type", "X-Request-ID"},
		ExposedHeaders:   []string{"Link", "X-Request-ID"},
		AllowCredentials: true,
		MaxAge:           300,
	}
}

// corsPolicy is the precomputed, request-independent form of a CORSConfig.
type corsPolicy struct {
	allowedOrigins   map[string]bool
	allowAnyOrigin   bool
	allowCredentials bool
	methodsStr       string
	headersStr       string
	exposedStr       string
	maxAgeStr        string
}

func newCORSPolicy(cfg CORSConfig) corsPolicy {
	p := corsPolicy{
		allowedOrigins:   make(map[string]bool, len(cfg.AllowedOrigins)),
		allowCredentials: cfg.AllowCredentials,
		methodsStr:       strings.Join(cfg.AllowedMethods, ", "),
		headersStr:       strings.Join(cfg.AllowedHeaders, ", "),
		exposedStr:       strings.Join(cfg.ExposedHeaders, ", "),
		maxAgeStr:        strconv.Itoa(cfg.MaxAge),
	}
	for _, o := range cfg.AllowedOrigins {
		p.allowedOrigins[o] = true
		if o == "*" {
			p.allowAnyOrigin = true
		}
	}
	return p
}

// CORS returns an HTTP middleware that handles Cross-Origin Resource Sharing.
func CORS(cfg CORSConfig) func(http.Handler) http.Handler {
	policy := newCORSPolicy(cfg)

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			origin := r.Header.Get("Origin")
			if !policy.isOriginAllowed(origin) {
				next.ServeHTTP(w, r)
				return
			}

			policy.setOriginHeaders(w, origin)

			if r.Method == http.MethodOptions {
				policy.writePreflight(w)
				return
			}

			next.ServeHTTP(w, r)
		})
	}
}

// isOriginAllowed reports whether origin is on the allowlist. An empty Origin
// header (same-origin or non-browser request) is never treated as allowed.
func (p corsPolicy) isOriginAllowed(origin string) bool {
	if origin == "" {
		return false
	}
	return p.allowedOrigins[origin] || p.allowAnyOrigin
}

func (p corsPolicy) setOriginHeaders(w http.ResponseWriter, origin string) {
	h := w.Header()
	h.Set("Access-Control-Allow-Origin", origin)
	if p.allowCredentials {
		h.Set("Access-Control-Allow-Credentials", "true")
	}
	if p.exposedStr != "" {
		h.Set("Access-Control-Expose-Headers", p.exposedStr)
	}
	h.Set("Vary", "Origin")
}

func (p corsPolicy) writePreflight(w http.ResponseWriter) {
	h := w.Header()
	h.Set("Access-Control-Allow-Methods", p.methodsStr)
	h.Set("Access-Control-Allow-Headers", p.headersStr)
	h.Set("Access-Control-Max-Age", p.maxAgeStr)
	w.WriteHeader(http.StatusNoContent)
}
