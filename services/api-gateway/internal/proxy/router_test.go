package proxy

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	chimw "github.com/go-chi/chi/v5/middleware"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
)

func TestProxyPreservesTrustedForwardingChain(t *testing.T) {
	var forwardedFor string
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		forwardedFor = r.Header.Get("X-Forwarded-For")
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(backend.Close)

	handler := newProxyHandler(Route{
		Prefix:    "/api",
		TargetURL: backend.URL,
	}, RouterConfig{
		CBManager: NewCircuitBreakerManager(CircuitBreakerConfig{
			MaxRequests:  1,
			Interval:     time.Minute,
			Timeout:      time.Minute,
			FailureRatio: 1,
		}),
		Logger: zerolog.Nop(),
	})
	handlerWithClientIP := chimw.ClientIPFromXFFTrustedProxies(1)(handler)

	req := httptest.NewRequest(http.MethodGet, "/api/resource", nil)
	req.RemoteAddr = "10.0.0.2:1234"
	req.Header.Set("X-Forwarded-For", "198.51.100.10")
	rec := httptest.NewRecorder()

	handlerWithClientIP.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code)
	assert.Equal(t, "198.51.100.10, 10.0.0.2", forwardedFor)
}
