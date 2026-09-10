package delivery

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/store"
	"github.com/google/uuid"
	"github.com/rs/zerolog"
)

func TestWorkerRetriesAndDelivers(t *testing.T) {
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		if calls.Add(1) <= 2 {
			http.Error(w, "temporary", http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()
	memory := store.NewMemoryStore()
	sub := store.Subscription{ID: uuid.New(), OwnerID: "owner", TargetURL: server.URL, Secret: "secret", Active: true, CreatedAt: time.Now().UTC(), UpdatedAt: time.Now().UTC()}
	if err := memory.CreateSubscription(context.Background(), &sub); err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	delivery := store.Delivery{ID: uuid.New(), SubscriptionID: sub.ID, EventType: "webhook.ping", Payload: []byte(`{"message":"ping"}`), MaxAttempts: 5, NextAttemptAt: now, CreatedAt: now, UpdatedAt: now}
	if err := memory.EnqueueDelivery(context.Background(), &delivery); err != nil {
		t.Fatal(err)
	}
	worker := NewWorker(memory, server.Client(), time.Second, 2*time.Second, zerolog.Nop(), true)
	for i := 0; i < 3; i++ {
		items, err := memory.ListDeliveries(context.Background(), "owner", nil, 10)
		if err != nil {
			t.Fatal(err)
		}
		if err := worker.deliver(context.Background(), items[0]); err != nil {
			t.Fatal(err)
		}
	}
	items, err := memory.ListDeliveries(context.Background(), "owner", nil, 10)
	if err != nil {
		t.Fatal(err)
	}
	if items[0].Status != "delivered" || items[0].Attempts != 3 {
		t.Fatalf("delivery=%+v", items[0])
	}
	if len(items[0].AttemptsLog) != 3 {
		t.Fatalf("attempts=%d", len(items[0].AttemptsLog))
	}
}

func TestWorkerDeadLettersAtMaxAttempts(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusInternalServerError) }))
	defer server.Close()
	memory := store.NewMemoryStore()
	sub := store.Subscription{ID: uuid.New(), OwnerID: "owner", TargetURL: server.URL, Secret: "secret", Active: true, CreatedAt: time.Now().UTC(), UpdatedAt: time.Now().UTC()}
	_ = memory.CreateSubscription(context.Background(), &sub)
	now := time.Now().UTC()
	_ = memory.EnqueueDelivery(context.Background(), &store.Delivery{ID: uuid.New(), SubscriptionID: sub.ID, EventType: "webhook.ping", Payload: []byte(`{}`), MaxAttempts: 5, NextAttemptAt: now, CreatedAt: now, UpdatedAt: now})
	worker := NewWorker(memory, server.Client(), time.Second, 2*time.Second, zerolog.Nop(), true)
	for i := 0; i < 5; i++ {
		items, _ := memory.ListDeliveries(context.Background(), "owner", nil, 10)
		if err := worker.deliver(context.Background(), items[0]); err != nil {
			t.Fatal(err)
		}
	}
	items, _ := memory.ListDeliveries(context.Background(), "owner", nil, 10)
	if items[0].Status != "failed" || items[0].Attempts != 5 {
		t.Fatalf("delivery=%+v", items[0])
	}
}
