package proxy

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
)

func TestRouterReturnsJSONForUnknownRoute(t *testing.T) {
	router := NewRouter(RouterConfig{
		CBManager: NewCircuitBreakerManager(defaultTestConfig()),
		Logger:    zerolog.Nop(),
	})

	req := httptest.NewRequest(http.MethodGet, "/unknown", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusNotFound, rec.Code)
	assert.Equal(t, "application/json", rec.Header().Get("Content-Type"))
	assert.JSONEq(t, `{"error":"route not found"}`, rec.Body.String())
}
