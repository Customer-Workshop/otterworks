package httpapi

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/store"
	"github.com/go-chi/chi/v5"
	"github.com/rs/zerolog"
)

func TestHeadlessRoutes(t *testing.T) {
	router := NewRouter(store.NewMemoryStore(), zerolog.Nop())
	routes := []struct{ method, path string }{
		{"GET", "/health"}, {"POST", "/api/v1/webhooks/subscriptions"}, {"GET", "/api/v1/webhooks/subscriptions"},
		{"GET", "/api/v1/webhooks/subscriptions/{id}"}, {"DELETE", "/api/v1/webhooks/subscriptions/{id}"},
		{"POST", "/api/v1/webhooks/subscriptions/{id}/test"}, {"GET", "/api/v1/webhooks/deliveries"},
	}
	if err := chi.Walk(router, func(method string, path string, _ http.Handler, _ ...func(http.Handler) http.Handler) error {
		path = strings.ReplaceAll(path, "{id}", "00000000-0000-0000-0000-000000000001")
		request := httptest.NewRequest(method, path, nil)
		if strings.HasPrefix(path, "/api/v1/webhooks") {
			request.Header.Set("X-User-ID", "owner")
		}
		response := httptest.NewRecorder()
		router.ServeHTTP(response, request)
		if got := response.Header().Get("Content-Type"); len(got) < len("application/json") || got[:len("application/json")] != "application/json" {
			t.Errorf("%s %s content-type=%q", method, path, got)
		}
		if response.Header().Get("Set-Cookie") != "" {
			t.Errorf("%s set a cookie", path)
		}
		if response.Body.Len() > 0 && !json.Valid(response.Body.Bytes()) {
			t.Errorf("%s returned invalid JSON", path)
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	for _, route := range routes {
		_ = route
	}
	for _, accept := range []string{"/", "/nope"} {
		req := httptest.NewRequest(http.MethodGet, accept, nil)
		resp := httptest.NewRecorder()
		router.ServeHTTP(resp, req)
		if resp.Code != 404 {
			t.Errorf("%s status=%d", accept, resp.Code)
		}
	}
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	req.Header.Set("Accept", "text/html")
	resp := httptest.NewRecorder()
	router.ServeHTTP(resp, req)
	if resp.Code != 406 {
		t.Fatalf("Accept status=%d", resp.Code)
	}
}
