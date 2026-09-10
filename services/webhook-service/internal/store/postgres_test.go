package store

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/google/uuid"
)

func TestPostgresStoreLifecycle(t *testing.T) {
	dsn := os.Getenv("WEBHOOK_TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("WEBHOOK_TEST_DATABASE_URL is not set")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	first, err := NewPostgresStore(ctx, dsn, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	defer first.Close()
	second, err := NewPostgresStore(ctx, dsn, time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	defer second.Close()

	owner := "postgres-test-" + uuid.NewString()
	subscription := &Subscription{
		ID:          uuid.New(),
		OwnerID:     owner,
		TargetURL:   "https://example.test/webhook",
		EventTypes:  []string{"webhook.ping"},
		Description: "integration test",
		Secret:      "whsec_test",
		Active:      true,
		CreatedAt:   time.Now().UTC(),
		UpdatedAt:   time.Now().UTC(),
	}
	defer func() {
		_ = first.DeleteSubscription(context.Background(), owner, subscription.ID)
	}()
	if err := first.CreateSubscription(ctx, subscription); err != nil {
		t.Fatal(err)
	}
	list, err := first.ListSubscriptions(ctx, owner)
	if err != nil || len(list) != 1 {
		t.Fatalf("subscriptions=%+v err=%v", list, err)
	}
	got, err := first.GetSubscription(ctx, owner, subscription.ID)
	if err != nil || got.ID != subscription.ID {
		t.Fatalf("subscription=%+v err=%v", got, err)
	}

	now := time.Now().UTC()
	delivery := &Delivery{
		ID:             uuid.New(),
		SubscriptionID: subscription.ID,
		EventType:      "webhook.ping",
		Payload:        []byte(`{"message":"ping"}`),
		MaxAttempts:    5,
		NextAttemptAt:  now,
		CreatedAt:      now,
		UpdatedAt:      now,
	}
	if err := first.EnqueueDelivery(ctx, delivery); err != nil {
		t.Fatal(err)
	}
	claimed, err := first.ClaimDueDeliveries(ctx, 10)
	if err != nil || len(claimed) != 1 {
		t.Fatalf("claimed=%+v err=%v", claimed, err)
	}
	claimedAgain, err := first.ClaimDueDeliveries(ctx, 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(claimedAgain) != 0 {
		t.Fatalf("claimed same delivery during lease: %+v", claimedAgain)
	}

	responseCode := 500
	lastError := "temporary failure"
	if err := first.RecordAttempt(ctx, &DeliveryAttempt{
		ID:           uuid.New(),
		DeliveryID:   delivery.ID,
		Attempt:      1,
		ResponseCode: &responseCode,
		Error:        &lastError,
		DurationMS:   12,
		AttemptedAt:  time.Now().UTC(),
	}); err != nil {
		t.Fatal(err)
	}
	deliveries, err := first.ListDeliveries(ctx, owner, &subscription.ID, 10)
	if err != nil || len(deliveries) != 1 || len(deliveries[0].AttemptsLog) != 1 {
		t.Fatalf("deliveries=%+v err=%v", deliveries, err)
	}
	if err := first.MarkRetry(ctx, delivery.ID, time.Now().UTC()); err != nil {
		t.Fatal(err)
	}
	if err := first.MarkFailed(ctx, delivery.ID); err != nil {
		t.Fatal(err)
	}

	delivered := &Delivery{
		ID:             uuid.New(),
		SubscriptionID: subscription.ID,
		EventType:      "webhook.ping",
		Payload:        []byte(`{"message":"delivered"}`),
		MaxAttempts:    5,
		NextAttemptAt:  time.Now().UTC(),
		CreatedAt:      time.Now().UTC(),
		UpdatedAt:      time.Now().UTC(),
	}
	if err := first.EnqueueDelivery(ctx, delivered); err != nil {
		t.Fatal(err)
	}
	if _, err := first.ClaimDueDeliveries(ctx, 10); err != nil {
		t.Fatal(err)
	}
	if err := first.MarkDelivered(ctx, delivered.ID, time.Now().UTC()); err != nil {
		t.Fatal(err)
	}

	if err := first.DeleteSubscription(ctx, owner, subscription.ID); err != nil {
		t.Fatal(err)
	}
	if _, err := first.GetSubscription(ctx, owner, subscription.ID); err != ErrNotFound {
		t.Fatalf("deleted subscription err=%v", err)
	}
}
