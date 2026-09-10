package store

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
)

func TestMemoryStoreClaimLease(t *testing.T) {
	memory := NewMemoryStore(time.Minute)
	now := time.Now().UTC()
	subscription := &Subscription{
		ID:         uuid.New(),
		OwnerID:    "owner",
		TargetURL:  "https://example.test/webhook",
		Secret:     "secret",
		Active:     true,
		CreatedAt:  now,
		UpdatedAt:  now,
		EventTypes: []string{"webhook.ping"},
	}
	if err := memory.CreateSubscription(context.Background(), subscription); err != nil {
		t.Fatal(err)
	}
	delivery := &Delivery{
		ID:             uuid.New(),
		SubscriptionID: subscription.ID,
		EventType:      "webhook.ping",
		Payload:        []byte(`{}`),
		NextAttemptAt:  now,
		CreatedAt:      now,
		UpdatedAt:      now,
	}
	if err := memory.EnqueueDelivery(context.Background(), delivery); err != nil {
		t.Fatal(err)
	}
	claimed, err := memory.ClaimDueDeliveries(context.Background(), 1)
	if err != nil || len(claimed) != 1 {
		t.Fatalf("claimed=%+v err=%v", claimed, err)
	}
	if claimedAgain, err := memory.ClaimDueDeliveries(context.Background(), 1); err != nil || len(claimedAgain) != 0 {
		t.Fatalf("claimed again=%+v err=%v", claimedAgain, err)
	}
}
