package consumer

import (
	"context"
	"testing"
	"time"

	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/store"
	"github.com/google/uuid"
	"github.com/rs/zerolog"
)

func TestParseRawAndSNSShapes(t *testing.T) {
	cases := []struct {
		name, body string
	}{
		{"raw file", `{"event_type":"file_shared","file_id":"f1","owner_id":"o1","timestamp":"2024-01-01T00:00:00Z"}`},
		{"file service event", `{"eventType":"file_shared","fileId":"f1","ownerId":"o1","sharedWithUserId":"u1","timestamp":"2024-01-01T00:00:00Z"}`},
		{"SNS document", `{"Type":"Notification","Message":"{\"event_type\":\"document_updated\",\"timestamp\":\"2024-01-01T00:00:00Z\",\"payload\":{\"document_id\":\"d1\"}}"}`},
		{"raw comment", `{"event_type":"comment_added","timestamp":"2024-01-01T00:00:00Z","payload":{"comment_id":"c1"}}`},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			event, err := ParseMessage(tc.body)
			if err != nil || event == nil {
				t.Fatalf("parse: event=%v err=%v", event, err)
			}
		})
	}
}
func TestUnknownEventIgnored(t *testing.T) {
	event, err := ParseMessage(`{"event_type":"unrelated","timestamp":"2024-01-01T00:00:00Z"}`)
	if err != nil || event != nil {
		t.Fatalf("event=%v err=%v", event, err)
	}
}

func TestParseMessageID(t *testing.T) {
	event, err := ParseMessageWithID(`{"MessageId":"sns-id","Message":"{\"event_type\":\"file_shared\"}"}`, "sqs-id")
	if err != nil || event == nil || event.MessageID != "sns-id" {
		t.Fatalf("event=%+v err=%v", event, err)
	}
	event, err = ParseMessageWithID(`{"event_type":"file_shared"}`, "sqs-id")
	if err != nil || event == nil || event.MessageID != "sqs-id" {
		t.Fatalf("event=%+v err=%v", event, err)
	}
}

func TestEnqueueRedeliveryIsIdempotent(t *testing.T) {
	memory := store.NewMemoryStore()
	now := time.Now().UTC()
	subscription := &store.Subscription{ID: uuid.New(), OwnerID: "owner", TargetURL: "https://example.test/webhook", Secret: "secret", Active: true, EventTypes: []string{"file.shared"}, CreatedAt: now, UpdatedAt: now}
	if err := memory.CreateSubscription(context.Background(), subscription); err != nil {
		t.Fatal(err)
	}
	consumer := New(nil, "", memory, zerolog.Nop(), 10)
	event := &ParsedEvent{BusType: "file_shared", WebhookType: "file.shared", OccurredAt: now, Data: map[string]string{"file_id": "f1"}, MessageID: "message-1"}
	if err := consumer.enqueue(context.Background(), event); err != nil {
		t.Fatal(err)
	}
	if err := consumer.enqueue(context.Background(), event); err != nil {
		t.Fatal(err)
	}
	deliveries, err := memory.ListDeliveries(context.Background(), "owner", nil, 10)
	if err != nil || len(deliveries) != 1 {
		t.Fatalf("deliveries=%+v err=%v", deliveries, err)
	}
}
