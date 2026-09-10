package httpapi

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/store"
	"github.com/rs/zerolog"
)

func TestSubscriptionAPI(t *testing.T) {
	router := NewRouter(store.NewMemoryStore(), zerolog.Nop(), Options{AllowPrivateTargets: true})

	response := serveAPI(router, http.MethodGet, "/api/v1/webhooks/subscriptions", "", "")
	if response.Code != http.StatusUnauthorized {
		t.Fatalf("missing identity status=%d", response.Code)
	}

	for _, body := range []string{
		`{"target_url":"ftp://example.test","event_types":["webhook.ping"]}`,
		`{"target_url":"https://example.test","event_types":[]}`,
		`{"target_url":"https://example.test","event_types":["unknown.event"]}`,
		`{"target_url":"https://example.test","event_types":[}`,
	} {
		response = serveAPI(router, http.MethodPost, "/api/v1/webhooks/subscriptions", "owner-a", body)
		if response.Code != http.StatusBadRequest {
			t.Errorf("body=%s status=%d", body, response.Code)
		}
	}

	response = serveAPI(router, http.MethodPost, "/api/v1/webhooks/subscriptions", "owner-a", `{"target_url":"https://example.test","event_types":["webhook.ping"]}`)
	if response.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", response.Code, response.Body.String())
	}
	var created map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &created); err != nil {
		t.Fatal(err)
	}
	id := created["id"].(string)
	secret := created["secret"].(string)
	if !strings.HasPrefix(secret, "whsec_") {
		t.Fatalf("secret=%q", secret)
	}

	response = serveAPI(router, http.MethodGet, "/api/v1/webhooks/subscriptions", "owner-a", "")
	if response.Code != http.StatusOK || strings.Contains(response.Body.String(), "secret") {
		t.Fatalf("list status=%d body=%s", response.Code, response.Body.String())
	}
	response = serveAPI(router, http.MethodGet, "/api/v1/webhooks/subscriptions/"+id, "owner-a", "")
	if response.Code != http.StatusOK || strings.Contains(response.Body.String(), "secret") {
		t.Fatalf("get status=%d body=%s", response.Code, response.Body.String())
	}
	response = serveAPI(router, http.MethodGet, "/api/v1/webhooks/subscriptions/"+id, "owner-b", "")
	if response.Code != http.StatusNotFound {
		t.Fatalf("cross-owner get status=%d", response.Code)
	}
	response = serveAPI(router, http.MethodDelete, "/api/v1/webhooks/subscriptions/"+id, "owner-b", "")
	if response.Code != http.StatusNotFound {
		t.Fatalf("cross-owner delete status=%d", response.Code)
	}

	response = serveAPI(router, http.MethodPost, "/api/v1/webhooks/subscriptions/"+id+"/test", "owner-a", "")
	if response.Code != http.StatusAccepted {
		t.Fatalf("test ping status=%d body=%s", response.Code, response.Body.String())
	}
	response = serveAPI(router, http.MethodGet, "/api/v1/webhooks/deliveries?subscription_id="+id, "owner-a", "")
	if response.Code != http.StatusOK {
		t.Fatalf("deliveries status=%d body=%s", response.Code, response.Body.String())
	}
	var deliveries struct {
		Data []struct {
			EventType string `json:"event_type"`
			Status    string `json:"status"`
		} `json:"data"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &deliveries); err != nil {
		t.Fatal(err)
	}
	if len(deliveries.Data) != 1 || deliveries.Data[0].EventType != "webhook.ping" || deliveries.Data[0].Status != "pending" {
		t.Fatalf("deliveries=%+v", deliveries.Data)
	}
	response = serveAPI(router, http.MethodGet, "/api/v1/webhooks/deliveries?subscription_id=bad", "owner-a", "")
	if response.Code != http.StatusBadRequest {
		t.Fatalf("invalid subscription id status=%d", response.Code)
	}

	response = serveAPI(router, http.MethodDelete, "/api/v1/webhooks/subscriptions/"+id, "owner-a", "")
	if response.Code != http.StatusNoContent {
		t.Fatalf("delete status=%d", response.Code)
	}
	response = serveAPI(router, http.MethodGet, "/api/v1/webhooks/subscriptions/"+id, "owner-a", "")
	if response.Code != http.StatusNotFound {
		t.Fatalf("deleted get status=%d", response.Code)
	}
}

func serveAPI(router http.Handler, method, path, owner, body string) *httptest.ResponseRecorder {
	request := httptest.NewRequest(method, path, bytes.NewBufferString(body))
	if owner != "" {
		request.Header.Set("X-User-ID", owner)
	}
	if body != "" {
		request.Header.Set("Content-Type", "application/json")
	}
	response := httptest.NewRecorder()
	router.ServeHTTP(response, request)
	return response
}
