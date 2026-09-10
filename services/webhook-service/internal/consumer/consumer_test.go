package consumer

import (
	"context"
	"encoding/json"
	"errors"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/aws/aws-sdk-go-v2/service/sqs/types"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/events"
	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/store"
)

type fakeSQS struct {
	messages []types.Message
	deleted  []string
	sent     []string
}

func (f *fakeSQS) ReceiveMessage(context.Context, *sqs.ReceiveMessageInput, ...func(*sqs.Options)) (*sqs.ReceiveMessageOutput, error) {
	out := &sqs.ReceiveMessageOutput{Messages: f.messages}
	f.messages = nil
	return out, nil
}

func (f *fakeSQS) DeleteMessage(_ context.Context, in *sqs.DeleteMessageInput, _ ...func(*sqs.Options)) (*sqs.DeleteMessageOutput, error) {
	f.deleted = append(f.deleted, aws.ToString(in.ReceiptHandle))
	return &sqs.DeleteMessageOutput{}, nil
}

func (f *fakeSQS) SendMessage(_ context.Context, in *sqs.SendMessageInput, _ ...func(*sqs.Options)) (*sqs.SendMessageOutput, error) {
	f.sent = append(f.sent, aws.ToString(in.MessageBody))
	return &sqs.SendMessageOutput{}, nil
}

type fakeEnqueuer struct {
	seen []string
	err  error
}

func (e *fakeEnqueuer) Enqueue(_ context.Context, ev *events.Event) (int, error) {
	if e.err != nil {
		return 0, e.err
	}
	e.seen = append(e.seen, ev.Type)
	return 1, nil
}

func msg(handle, body string) types.Message {
	return types.Message{MessageId: aws.String(handle), ReceiptHandle: aws.String(handle), Body: aws.String(body)}
}

func TestPollOnceDeletesHandledAndPoisonMessages(t *testing.T) {
	q := &fakeSQS{messages: []types.Message{
		msg("h1", `{"Type":"Notification","MessageId":"m1","Message":"{\"eventType\":\"file_uploaded\",\"fileId\":\"f1\"}"}`),
		msg("h2", `{"event_type":"document_created","payload":{"id":"d1"}}`),
		msg("h3", `not json at all`),
	}}
	enq := &fakeEnqueuer{}
	c := New(q, "http://q", 1, enq, zerolog.Nop())
	require.NoError(t, c.PollOnce(context.Background()))
	assert.Equal(t, []string{"file_uploaded", "document_created"}, enq.seen)
	assert.ElementsMatch(t, []string{"h1", "h2", "h3"}, q.deleted, "poison message is dropped, handled ones are acked")
}

func TestPollOnceLeavesMessageWhenEnqueueFails(t *testing.T) {
	q := &fakeSQS{messages: []types.Message{msg("h1", `{"event_type":"comment_added","payload":{}}`)}}
	c := New(q, "http://q", 1, &fakeEnqueuer{err: errors.New("db down")}, zerolog.Nop())
	require.NoError(t, c.PollOnce(context.Background()))
	assert.Empty(t, q.deleted, "message stays visible for SQS redelivery")
}

func TestDLQPublish(t *testing.T) {
	assert.Nil(t, NewDLQ(&fakeSQS{}, ""), "no URL means no DLQ")
	q := &fakeSQS{}
	dlq := NewDLQ(q, "http://dlq")
	require.NotNil(t, dlq)
	err := dlq.Publish(context.Background(), &store.Delivery{ID: "d1", SubscriptionID: "s1", OwnerID: "alice", EventID: "e1", EventType: "file_deleted", Attempts: 6, LastStatusCode: 502, Payload: []byte(`{"x":1}`)})
	require.NoError(t, err)
	require.Len(t, q.sent, 1)
	var body map[string]any
	require.NoError(t, json.Unmarshal([]byte(q.sent[0]), &body))
	assert.Equal(t, "d1", body["deliveryId"])
	assert.Equal(t, float64(6), body["attempts"])
	assert.Equal(t, map[string]any{"x": float64(1)}, body["payload"])
}
