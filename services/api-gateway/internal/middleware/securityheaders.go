package middleware

import (
	"bufio"
	"net"
	"net/http"
	"strconv"
)

// SecurityHeadersConfig controls the baseline response headers set on every response.
type SecurityHeadersConfig struct {
	// HSTSMaxAge is the max-age (seconds) for Strict-Transport-Security. Zero disables HSTS.
	HSTSMaxAge int
}

// DefaultSecurityHeadersConfig returns the headers applied when nothing is configured.
func DefaultSecurityHeadersConfig() SecurityHeadersConfig {
	return SecurityHeadersConfig{HSTSMaxAge: 31536000}
}

// SecurityHeaders returns middleware that sets baseline browser security headers on
// every response, including responses relayed from upstream services by the proxy
// and rejections written by later middleware.
func SecurityHeaders(cfg SecurityHeadersConfig) func(http.Handler) http.Handler {
	hsts := ""
	if cfg.HSTSMaxAge > 0 {
		hsts = "max-age=" + strconv.Itoa(cfg.HSTSMaxAge) + "; includeSubDomains"
	}
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			next.ServeHTTP(&securityHeaderWriter{ResponseWriter: w, hsts: hsts}, r)
		})
	}
}

type securityHeaderWriter struct {
	http.ResponseWriter
	hsts    string
	applied bool
}

func (w *securityHeaderWriter) apply() {
	if w.applied {
		return
	}
	w.applied = true
	h := w.Header()
	h.Set("X-Content-Type-Options", "nosniff")
	h.Set("X-Frame-Options", "DENY")
	h.Set("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
	h.Set("Referrer-Policy", "no-referrer")
	if h.Get("Cache-Control") == "" {
		h.Set("Cache-Control", "no-store")
	}
	if w.hsts != "" {
		h.Set("Strict-Transport-Security", w.hsts)
	}
}

func (w *securityHeaderWriter) WriteHeader(code int) {
	w.apply()
	w.ResponseWriter.WriteHeader(code)
}

func (w *securityHeaderWriter) Write(b []byte) (int, error) {
	w.apply()
	return w.ResponseWriter.Write(b)
}

func (w *securityHeaderWriter) Flush() {
	w.apply()
	_ = http.NewResponseController(w.ResponseWriter).Flush()
}

func (w *securityHeaderWriter) Hijack() (net.Conn, *bufio.ReadWriter, error) {
	w.apply()
	return http.NewResponseController(w.ResponseWriter).Hijack()
}

func (w *securityHeaderWriter) Unwrap() http.ResponseWriter {
	return w.ResponseWriter
}
