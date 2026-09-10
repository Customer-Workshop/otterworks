package api

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/store"
)

func newTestServer(t *testing.T) (http.Handler, *store.Memory) {
	t.Helper()
	mem := store.NewMemory()
	return New(mem, Options{MaxAttempts: 3, AllowPrivateTargets: true}, zerolog.Nop()), mem
}

func do(t *testing.T, h http.Handler, method, path, user string, body any) *httptest.ResponseRecorder {
	t.Helper()
	var buf bytes.Buffer
	if body != nil {
		require.NoError(t, json.NewEncoder(&buf).Encode(body))
	}
	req := httptest.NewRequest(method, path, &buf)
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if user != "" {
		req.Header.Set(HeaderUserID, user)
	}
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

// assertJSON is the headless contract: every response is JSON, never HTML.
func assertJSON(t *testing.T, rec *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	ct := rec.Header().Get("Content-Type")
	assert.True(t, strings.HasPrefix(ct, "application/json"), "content-type %q", ct)
	assert.NotContains(t, strings.ToLower(rec.Body.String()), "<html")
	var out map[string]any
	require.NoError(t, json.Unmarshal(rec.Body.Bytes(), &out), "body must be a JSON object: %s", rec.Body.String())
	return out
}

func TestEveryRouteIsJSON(t *testing.T) {
	h, _ := newTestServer(t)
	cases := []struct {
		method, path, user string
		want               int
	}{
		{"GET", "/health", "", 200},
		{"GET", "/ready", "", 200},
		{"GET", "/does-not-exist", "", 404},
		{"GET", "/index.html", "", 404},
		{"GET", "/static/app.js", "", 404},
		{"DELETE", "/health", "", 405},
		{"GET", "/api/v1/webhooks", "", 401},
		{"GET", "/api/v1/webhooks", "u1", 200},
		{"GET", "/api/v1/webhooks/event-types", "u1", 200},
		{"GET", "/api/v1/webhooks/stats", "u1", 200},
		{"GET", "/api/v1/webhooks/subscriptions", "u1", 200},
		{"GET", "/api/v1/webhooks/subscriptions/nope", "u1", 404},
		{"GET", "/api/v1/webhooks/subscriptions/" + uuid.NewString(), "u1", 404},
		{"DELETE", "/api/v1/webhooks/subscriptions/" + uuid.NewString(), "u1", 404},
		{"POST", "/api/v1/webhooks/subscriptions/nope/rotate-secret", "u1", 404},
		{"GET", "/api/v1/webhooks/deliveries", "u1", 200},
		{"GET", "/api/v1/webhooks/deliveries?status=bogus", "u1", 400},
		{"GET", "/api/v1/webhooks/deliveries/nope", "u1", 404},
		{"GET", "/api/v1/webhooks/dead-letters", "u1", 200},
		{"POST", "/api/v1/webhooks/deliveries/nope/replay", "u1", 404},
	}
	for _, c := range cases {
		t.Run(c.method+" "+c.path, func(t *testing.T) {
			rec := do(t, h, c.method, c.path, c.user, nil)
			assert.Equal(t, c.want, rec.Code)
			assertJSON(t, rec)
		})
	}
	// Browser-style Accept header still yields JSON.
	req := httptest.NewRequest("GET", "/", nil)
	req.Header.Set("Accept", "text/html")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	assert.Equal(t, 404, rec.Code)
	assertJSON(t, rec)
}

func TestSubscriptionCRUDAndOwnership(t *testing.T) {
	h, st := newTestServer(t)

	rec := do(t, h, "POST", "/api/v1/webhooks/subscriptions", "alice", map[string]any{
		"url": "http://sink:9000/hook", "eventTypes": []string{"file_uploaded"}, "description": "files",
	})
	require.Equal(t, 201, rec.Code, rec.Body.String())
	created := assertJSON(t, rec)
	id := created["id"].(string)
	assert.True(t, strings.HasPrefix(created["secret"].(string), "whsec_"), "secret returned once on create")

	rec = do(t, h, "GET", "/api/v1/webhooks/subscriptions/"+id, "alice", nil)
	require.Equal(t, 200, rec.Code)
	got := assertJSON(t, rec)
	_, hasSecret := got["secret"]
	assert.False(t, hasSecret, "secret must never be returned on read")

	rec = do(t, h, "GET", "/api/v1/webhooks/subscriptions/"+id, "bob", nil)
	assert.Equal(t, 404, rec.Code, "other owners cannot see the subscription")
	assertJSON(t, rec)

	rec = do(t, h, "PATCH", "/api/v1/webhooks/subscriptions/"+id, "alice", map[string]any{"active": false, "eventTypes": []string{"*"}})
	require.Equal(t, 200, rec.Code, rec.Body.String())
	assert.Equal(t, false, assertJSON(t, rec)["active"])

	rec = do(t, h, "GET", "/api/v1/webhooks/subscriptions", "alice", nil)
	assert.Equal(t, float64(1), assertJSON(t, rec)["count"])
	rec = do(t, h, "GET", "/api/v1/webhooks/subscriptions", "bob", nil)
	assert.Equal(t, float64(0), assertJSON(t, rec)["count"])

	rec = do(t, h, "POST", "/api/v1/webhooks/subscriptions/"+id+"/rotate-secret", "alice", nil)
	require.Equal(t, 200, rec.Code)
	rotated := assertJSON(t, rec)["secret"].(string)
	assert.NotEqual(t, created["secret"], rotated)

	rec = do(t, h, "PATCH", "/api/v1/webhooks/subscriptions/"+id, "alice", map[string]any{"description": "renamed"})
	require.Equal(t, 200, rec.Code)
	stored, err := st.GetSubscription(context.Background(), "alice", id)
	require.NoError(t, err)
	assert.Equal(t, rotated, stored.Secret, "PATCH never writes the secret column")

	rec = do(t, h, "DELETE", "/api/v1/webhooks/subscriptions/"+id, "bob", nil)
	assert.Equal(t, 404, rec.Code)
	rec = do(t, h, "DELETE", "/api/v1/webhooks/subscriptions/"+id, "alice", nil)
	assert.Equal(t, 200, rec.Code)
	rec = do(t, h, "GET", "/api/v1/webhooks/subscriptions/"+id, "alice", nil)
	assert.Equal(t, 404, rec.Code)
}

func TestDeliveryFilterValidation(t *testing.T) {
	h, _ := newTestServer(t)
	for _, q := range []string{
		"subscriptionId=not-a-uuid",
		"cursor=" + base64.RawURLEncoding.EncodeToString([]byte("garbage")),
		"cursor=" + base64.RawURLEncoding.EncodeToString([]byte("2026-01-01T00:00:00Z|not-a-uuid")),
		"limit=0",
		"status=bogus",
		"since=yesterday",
	} {
		rec := do(t, h, http.MethodGet, "/api/v1/webhooks/deliveries?"+q, "alice", nil)
		body := assertJSON(t, rec)
		assert.Equal(t, http.StatusBadRequest, rec.Code, q)
		assert.Equal(t, "validation_error", body["error"], q)
	}
	rec := do(t, h, http.MethodGet, "/api/v1/webhooks/deliveries?subscriptionId="+uuid.NewString()+"&limit=5", "alice", nil)
	assert.Equal(t, http.StatusOK, rec.Code)
}

func TestSubscriptionValidation(t *testing.T) {
	h, _ := newTestServer(t)
	bad := []map[string]any{
		{"eventTypes": []string{"file_uploaded"}},
		{"url": "ftp://x/y", "eventTypes": []string{"file_uploaded"}},
		{"url": "http://sink/x", "eventTypes": []string{}},
		{"url": "http://sink/x", "eventTypes": []string{"nope"}},
		{"url": "http://sink/x", "eventTypes": []string{"*"}, "secret": "short"},
		{"url": "http://sink/x", "eventTypes": []string{"*"}, "unknown": 1},
	}
	for i, b := range bad {
		rec := do(t, h, "POST", "/api/v1/webhooks/subscriptions", "alice", b)
		assert.Equal(t, 400, rec.Code, "case %d: %s", i, rec.Body.String())
		assertJSON(t, rec)
	}
	req := httptest.NewRequest("POST", "/api/v1/webhooks/subscriptions", strings.NewReader("<html>"))
	req.Header.Set(HeaderUserID, "alice")
	req.Header.Set("Content-Type", "text/html")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	assert.Equal(t, 400, rec.Code)
	assertJSON(t, rec)
}

func TestPrivateTargetsRejectedByDefault(t *testing.T) {
	h := New(store.NewMemory(), Options{MaxAttempts: 3}, zerolog.Nop())
	for _, u := range []string{"http://example.com/x", "https://localhost/x", "https://127.0.0.1/x", "https://10.0.0.5/x"} {
		rec := do(t, h, "POST", "/api/v1/webhooks/subscriptions", "alice", map[string]any{"url": u, "eventTypes": []string{"*"}})
		assert.Equal(t, 400, rec.Code, u)
		assertJSON(t, rec)
	}
	rec := do(t, h, "POST", "/api/v1/webhooks/subscriptions", "alice", map[string]any{"url": "https://hooks.example.com/x", "eventTypes": []string{"*"}})
	assert.Equal(t, 201, rec.Code)
}

func TestDeliveryLogReplayAndDeadLetters(t *testing.T) {
	h, mem := newTestServer(t)
	ctx := context.Background()
	rec := do(t, h, "POST", "/api/v1/webhooks/subscriptions", "alice", map[string]any{"url": "http://sink/x", "eventTypes": []string{"*"}})
	require.Equal(t, 201, rec.Code)
	subID := assertJSON(t, rec)["id"].(string)

	rec = do(t, h, "POST", "/api/v1/webhooks/subscriptions/"+subID+"/test", "alice", nil)
	require.Equal(t, 202, rec.Code, rec.Body.String())
	del := assertJSON(t, rec)
	delID := del["id"].(string)
	assert.Equal(t, "pending", del["status"])

	rec = do(t, h, "GET", "/api/v1/webhooks/deliveries?subscriptionId="+subID+"&status=pending", "alice", nil)
	assert.Equal(t, float64(1), assertJSON(t, rec)["count"])
	rec = do(t, h, "GET", "/api/v1/webhooks/deliveries", "bob", nil)
	assert.Equal(t, float64(0), assertJSON(t, rec)["count"], "deliveries are owner scoped")

	// Drive the delivery to dead_letter through the store (3 failed attempts).
	for i := 1; i <= 3; i++ {
		due, err := mem.ClaimDueDeliveries(ctx, time.Now().Add(time.Hour), time.Minute, 10)
		require.NoError(t, err)
		require.Len(t, due, 1, "attempt %d", i)
		res := store.AttemptResult{StatusCode: 500, Error: "boom", AttemptedAt: time.Now()}
		if i < 3 {
			next := time.Now().Add(-time.Second)
			res.NextAttemptAt = &next
		} else {
			res.DeadLetter = true
		}
		require.NoError(t, mem.RecordAttempt(ctx, due[0], res))
	}

	rec = do(t, h, "GET", "/api/v1/webhooks/dead-letters", "alice", nil)
	dl := assertJSON(t, rec)
	require.Equal(t, float64(1), dl["count"])
	rec = do(t, h, "GET", "/api/v1/webhooks/deliveries/"+delID+"/attempts", "alice", nil)
	assert.Equal(t, float64(3), assertJSON(t, rec)["count"])
	rec = do(t, h, "GET", "/api/v1/webhooks/stats", "alice", nil)
	stats := assertJSON(t, rec)["deliveries"].(map[string]any)
	assert.Equal(t, float64(1), stats["dead_letter"])

	rec = do(t, h, "POST", "/api/v1/webhooks/deliveries/"+delID+"/replay", "alice", nil)
	require.Equal(t, 202, rec.Code, rec.Body.String())
	assert.Equal(t, "pending", assertJSON(t, rec)["status"])
	rec = do(t, h, "GET", "/api/v1/webhooks/dead-letters", "alice", nil)
	assert.Equal(t, float64(0), assertJSON(t, rec)["count"])
}
