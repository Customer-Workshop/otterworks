package dispatch

import (
	"context"
	"encoding/json"
	"io"
	"math/rand"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/events"
	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/signing"
	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/store"
)

type fakeDLQ struct {
	mu   sync.Mutex
	seen []string
}

func (f *fakeDLQ) Publish(_ context.Context, d *store.Delivery) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.seen = append(f.seen, d.ID)
	return nil
}

func newDispatcher(t *testing.T, st store.Store, dlq DeadLetterSink, maxAttempts int) *Dispatcher {
	t.Helper()
	return New(st, dlq, Options{
		Workers: 2, MaxAttempts: maxAttempts, BackoffBase: time.Millisecond, BackoffMax: 5 * time.Millisecond,
		Timeout: 2 * time.Second, AllowPrivateTargets: true,
	}, zerolog.Nop())
}

func addSub(t *testing.T, st store.Store, url string, types ...string) *store.Subscription {
	t.Helper()
	now := time.Now().UTC()
	s := &store.Subscription{ID: "sub-" + url[len(url)-4:], OwnerID: "alice", URL: url, EventTypes: types, Secret: "whsec_test_secret_0123456789", Active: true, CreatedAt: now, UpdatedAt: now}
	require.NoError(t, st.CreateSubscription(context.Background(), s))
	return s
}

func TestBackoffGrowsAndCaps(t *testing.T) {
	assert.Equal(t, 2*time.Second, Backoff(1, 2*time.Second, time.Minute, nil))
	assert.Equal(t, 4*time.Second, Backoff(2, 2*time.Second, time.Minute, nil))
	assert.Equal(t, 32*time.Second, Backoff(5, 2*time.Second, time.Minute, nil))
	assert.Equal(t, time.Minute, Backoff(10, 2*time.Second, time.Minute, nil), "capped")
	assert.Equal(t, time.Minute, Backoff(500, 2*time.Second, time.Minute, nil), "no overflow")
	rng := rand.New(rand.NewSource(1))
	for i := 0; i < 100; i++ {
		d := Backoff(3, time.Second, time.Minute, rng)
		assert.GreaterOrEqual(t, d, 2*time.Second, "jitter floor is half the exponential delay")
		assert.LessOrEqual(t, d, 4*time.Second)
	}
}

func TestEnqueueFansOutIdempotentlyAndSignsDelivery(t *testing.T) {
	ctx := context.Background()
	st := store.NewMemory()
	var got atomic.Int32
	var lastReq *http.Request
	var lastBody []byte
	var mu sync.Mutex
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		mu.Lock()
		lastReq, lastBody = r.Clone(ctx), b
		mu.Unlock()
		got.Add(1)
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	defer srv.Close()

	sub := addSub(t, st, srv.URL+"/aaaa", "file_uploaded")
	addSub(t, st, srv.URL+"/bbbb", "*")
	addSub(t, st, srv.URL+"/cccc", "document_created")
	inactive := addSub(t, st, srv.URL+"/dddd", "*")
	inactive.Active = false
	require.NoError(t, st.UpdateSubscription(ctx, inactive))

	d := newDispatcher(t, st, nil, 3)
	ev := &events.Event{ID: "evt-1", Type: "file_uploaded", Source: "file-service", OccurredAt: time.Now(), Data: json.RawMessage(`{"fileId":"f1"}`)}
	n, err := d.Enqueue(ctx, ev)
	require.NoError(t, err)
	assert.Equal(t, 2, n, "matching + wildcard, not inactive or other type")

	_, err = d.Enqueue(ctx, ev)
	require.NoError(t, err)
	dels, _, err := st.ListDeliveries(ctx, store.DeliveryFilter{OwnerID: "alice", Limit: 10})
	require.NoError(t, err)
	assert.Len(t, dels, 2, "redelivered SQS message must not create duplicate deliveries")

	processed, err := d.RunOnce(ctx)
	require.NoError(t, err)
	assert.Equal(t, 2, processed)
	assert.Equal(t, int32(2), got.Load())

	dels, _, _ = st.ListDeliveries(ctx, store.DeliveryFilter{OwnerID: "alice", Status: store.StatusDelivered, Limit: 10})
	assert.Len(t, dels, 2)

	mu.Lock()
	defer mu.Unlock()
	assert.Equal(t, "application/json", lastReq.Header.Get("Content-Type"))
	assert.Equal(t, "file_uploaded", lastReq.Header.Get(signing.HeaderEvent))
	assert.Equal(t, "evt-1", lastReq.Header.Get(signing.HeaderEventID))
	assert.NotEmpty(t, lastReq.Header.Get(signing.HeaderDeliveryID))
	require.NoError(t, signing.Verify(sub.Secret, lastReq.Header.Get(signing.HeaderSignature), lastBody, time.Now(), time.Minute))
	var payload map[string]any
	require.NoError(t, json.Unmarshal(lastBody, &payload))
	assert.Equal(t, "file_uploaded", payload["type"])
	assert.NotEmpty(t, payload["subscriptionId"])
}

func TestRetriesThenDeadLetters(t *testing.T) {
	ctx := context.Background()
	st := store.NewMemory()
	var hits atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits.Add(1)
		http.Error(w, `{"error":"nope"}`, http.StatusInternalServerError)
	}))
	defer srv.Close()
	addSub(t, st, srv.URL+"/fail", "*")
	dlq := &fakeDLQ{}
	d := newDispatcher(t, st, dlq, 3)

	_, err := d.Enqueue(ctx, &events.Event{ID: "evt-2", Type: "document_deleted", OccurredAt: time.Now(), Data: json.RawMessage(`{}`)})
	require.NoError(t, err)

	for attempt := 1; attempt <= 3; attempt++ {
		time.Sleep(10 * time.Millisecond) // > BackoffMax so the retry is due
		n, err := d.RunOnce(ctx)
		require.NoError(t, err)
		require.Equal(t, 1, n, "attempt %d should be due", attempt)
	}
	n, err := d.RunOnce(ctx)
	require.NoError(t, err)
	assert.Equal(t, 0, n, "nothing due after dead-lettering")
	assert.Equal(t, int32(3), hits.Load())

	dels, _, _ := st.ListDeliveries(ctx, store.DeliveryFilter{OwnerID: "alice", Limit: 10})
	require.Len(t, dels, 1)
	del := dels[0]
	assert.Equal(t, store.StatusDeadLetter, del.Status)
	assert.Equal(t, 3, del.Attempts)
	assert.Equal(t, 500, del.LastStatusCode)
	assert.NotNil(t, del.DeadLetteredAt)
	assert.Equal(t, []string{del.ID}, dlq.seen, "dead letter also published to the DLQ sink")

	attempts, err := st.ListAttempts(ctx, del.ID)
	require.NoError(t, err)
	require.Len(t, attempts, 3)
	for i, a := range attempts {
		assert.Equal(t, i+1, a.Number)
		assert.Equal(t, 500, a.StatusCode)
		assert.Contains(t, a.ResponseBody, "nope")
	}

	// Replay resets it and a now-healthy receiver gets it delivered.
	replayed, err := st.RequeueDelivery(ctx, "alice", del.ID, 3)
	require.NoError(t, err)
	assert.Equal(t, store.StatusPending, replayed.Status)
	srv.Config.Handler = http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(204) })
	n, err = d.RunOnce(ctx)
	require.NoError(t, err)
	assert.Equal(t, 1, n)
	got, _ := st.GetDelivery(ctx, "alice", del.ID)
	assert.Equal(t, store.StatusDelivered, got.Status)
}

func TestRetryingStatusBetweenAttempts(t *testing.T) {
	ctx := context.Background()
	st := store.NewMemory()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(503) }))
	defer srv.Close()
	addSub(t, st, srv.URL+"/slow", "*")
	d := New(st, nil, Options{Workers: 1, MaxAttempts: 5, BackoffBase: time.Hour, BackoffMax: time.Hour, AllowPrivateTargets: true}, zerolog.Nop())
	_, err := d.Enqueue(ctx, &events.Event{ID: "evt-3", Type: "comment_added", OccurredAt: time.Now(), Data: json.RawMessage(`{}`)})
	require.NoError(t, err)
	_, err = d.RunOnce(ctx)
	require.NoError(t, err)
	dels, _, _ := st.ListDeliveries(ctx, store.DeliveryFilter{OwnerID: "alice", Limit: 10})
	require.Len(t, dels, 1)
	assert.Equal(t, store.StatusRetrying, dels[0].Status)
	assert.Equal(t, 1, dels[0].Attempts)
	require.NotNil(t, dels[0].NextAttemptAt)
	assert.Greater(t, time.Until(*dels[0].NextAttemptAt), 20*time.Minute, "backoff scheduled far in the future")
	n, _ := d.RunOnce(ctx)
	assert.Equal(t, 0, n, "not due yet")
}

func TestValidateTargetURL(t *testing.T) {
	assert.NoError(t, ValidateTargetURL("https://hooks.example.com/x", false))
	assert.Error(t, ValidateTargetURL("http://hooks.example.com/x", false), "https required in strict mode")
	assert.Error(t, ValidateTargetURL("https://localhost/x", false))
	assert.Error(t, ValidateTargetURL("https://192.168.1.1/x", false))
	assert.Error(t, ValidateTargetURL("://bad", false))
	assert.Error(t, ValidateTargetURL("mailto:x@y", true))
	assert.NoError(t, ValidateTargetURL("http://localhost:9000/x", true))
}
