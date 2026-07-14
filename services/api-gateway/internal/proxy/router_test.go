package proxy

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestProxyUsesUpstreamHost(t *testing.T) {
	var receivedHost string
	var receivedPath string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedHost = r.Host
		receivedPath = r.URL.Path
		w.WriteHeader(http.StatusNoContent)
	}))
	defer upstream.Close()

	handler := newProxyHandler(Route{
		Prefix:    "/api/v1/reports",
		TargetURL: upstream.URL,
	}, RouterConfig{
		CBManager: NewCircuitBreakerManager(defaultTestConfig()),
		Logger:    zerolog.Nop(),
	})

	request := httptest.NewRequest(http.MethodGet, "/api/v1/reports/42", nil)
	request.Host = "gateway.example.test"
	response := httptest.NewRecorder()

	handler(response, request)

	require.Equal(t, http.StatusNoContent, response.Code)
	assert.Equal(t, upstream.Listener.Addr().String(), receivedHost)
	assert.Equal(t, "/api/v1/reports/42", receivedPath)
}
