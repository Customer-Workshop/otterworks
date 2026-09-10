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
	router := NewRouter(store.NewMemoryStore(), zerolog.Nop(), Options{AllowPrivateTargets: true})
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
	for _, accept := range []string{"/", "/nope"} {
		req := httptest.NewRequest(http.MethodGet, accept, nil)
		resp := httptest.NewRecorder()
		router.ServeHTTP(resp, req)
		if resp.Code != 404 {
			t.Errorf("%s status=%d", accept, resp.Code)
		}
		assertHeadlessResponse(t, resp)
	}
	for _, test := range []struct {
		method string
		path   string
	}{
		{http.MethodPost, "/api/v1/webhooks/subscriptions"},
		{http.MethodGet, "/nope"},
	} {
		req := httptest.NewRequest(test.method, test.path, strings.NewReader(`{}`))
		req.Header.Set("Accept", "text/html")
		resp := httptest.NewRecorder()
		router.ServeHTTP(resp, req)
		if resp.Code != http.StatusNotAcceptable {
			t.Errorf("%s %s status=%d", test.method, test.path, resp.Code)
		}
		assertHeadlessResponse(t, resp)
	}
}

func assertHeadlessResponse(t *testing.T, response *httptest.ResponseRecorder) {
	t.Helper()
	if got := response.Header().Get("Content-Type"); !strings.HasPrefix(got, "application/json") {
		t.Errorf("content-type=%q", got)
	}
	if response.Header().Get("Set-Cookie") != "" {
		t.Error("response set a cookie")
	}
	if response.Body.Len() > 0 && !json.Valid(response.Body.Bytes()) {
		t.Error("response body is not JSON")
	}
}
