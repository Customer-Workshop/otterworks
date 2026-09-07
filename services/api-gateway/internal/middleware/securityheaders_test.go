package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
)

func okHandler(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(`{}`))
}

func TestSecurityHeaders_SetOnEveryResponse(t *testing.T) {
	handler := SecurityHeaders(DefaultSecurityHeadersConfig())(http.HandlerFunc(okHandler))

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/api/v1/documents/", nil))

	h := rec.Header()
	assert.Equal(t, "nosniff", h.Get("X-Content-Type-Options"))
	assert.Equal(t, "DENY", h.Get("X-Frame-Options"))
	assert.Equal(t, "default-src 'none'; frame-ancestors 'none'", h.Get("Content-Security-Policy"))
	assert.Equal(t, "no-referrer", h.Get("Referrer-Policy"))
	assert.Equal(t, "no-store", h.Get("Cache-Control"))
	assert.Equal(t, "max-age=31536000; includeSubDomains", h.Get("Strict-Transport-Security"))
}

func TestSecurityHeaders_SetOnRejection(t *testing.T) {
	handler := SecurityHeaders(DefaultSecurityHeadersConfig())(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "nope", http.StatusUnauthorized)
	}))

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/api/v1/files", nil))

	assert.Equal(t, http.StatusUnauthorized, rec.Code)
	assert.Equal(t, "nosniff", rec.Header().Get("X-Content-Type-Options"))
	assert.Equal(t, "DENY", rec.Header().Get("X-Frame-Options"))
}

func TestSecurityHeaders_ImplicitWriteHeader(t *testing.T) {
	handler := SecurityHeaders(DefaultSecurityHeadersConfig())(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("body"))
	}))

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/", nil))

	assert.Equal(t, http.StatusOK, rec.Code)
	assert.Equal(t, "no-referrer", rec.Header().Get("Referrer-Policy"))
}

func TestSecurityHeaders_OverridesUpstreamButKeepsCacheControl(t *testing.T) {
	handler := SecurityHeaders(DefaultSecurityHeadersConfig())(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Frame-Options", "ALLOWALL")
		w.Header().Set("Cache-Control", "private, max-age=60")
		w.WriteHeader(http.StatusOK)
	}))

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/", nil))

	assert.Equal(t, "DENY", rec.Header().Get("X-Frame-Options"))
	assert.Equal(t, []string{"DENY"}, rec.Header().Values("X-Frame-Options"))
	assert.Equal(t, "private, max-age=60", rec.Header().Get("Cache-Control"))
}

func TestSecurityHeaders_HSTSDisabled(t *testing.T) {
	handler := SecurityHeaders(SecurityHeadersConfig{HSTSMaxAge: 0})(http.HandlerFunc(okHandler))

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/", nil))

	assert.Empty(t, rec.Header().Get("Strict-Transport-Security"))
	assert.Equal(t, "nosniff", rec.Header().Get("X-Content-Type-Options"))
}

func TestSecurityHeaders_PreservesFlusher(t *testing.T) {
	var flushed bool
	handler := SecurityHeaders(DefaultSecurityHeadersConfig())(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		f, ok := w.(http.Flusher)
		if ok {
			f.Flush()
			flushed = true
		}
	}))

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/", nil))

	assert.True(t, flushed)
	assert.True(t, rec.Flushed)
	assert.Equal(t, "nosniff", rec.Header().Get("X-Content-Type-Options"))
}
