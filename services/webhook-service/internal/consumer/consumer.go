// Package consumer long-polls the webhook SQS queue (subscribed to the
// otterworks-events SNS topic) and hands each event to the dispatcher.
package consumer

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/aws/aws-sdk-go-v2/service/sqs/types"
	"github.com/rs/zerolog"

	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/events"
	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/store"
)

// SQSAPI is the subset of the SQS client used here (mockable in tests).
type SQSAPI interface {
	ReceiveMessage(ctx context.Context, in *sqs.ReceiveMessageInput, opts ...func(*sqs.Options)) (*sqs.ReceiveMessageOutput, error)
	DeleteMessage(ctx context.Context, in *sqs.DeleteMessageInput, opts ...func(*sqs.Options)) (*sqs.DeleteMessageOutput, error)
	SendMessage(ctx context.Context, in *sqs.SendMessageInput, opts ...func(*sqs.Options)) (*sqs.SendMessageOutput, error)
}

// Enqueuer is satisfied by dispatch.Dispatcher.
type Enqueuer interface {
	Enqueue(ctx context.Context, ev *events.Event) (int, error)
}

// Consumer drains the events queue.
type Consumer struct {
	sqs      SQSAPI
	queueURL string
	wait     int32
	enq      Enqueuer
	log      zerolog.Logger
}

// New builds a consumer.
func New(client SQSAPI, queueURL string, waitSeconds int32, enq Enqueuer, log zerolog.Logger) *Consumer {
	if waitSeconds <= 0 {
		waitSeconds = 10
	}
	return &Consumer{sqs: client, queueURL: queueURL, wait: waitSeconds, enq: enq, log: log.With().Str("component", "consumer").Logger()}
}

// Run polls until ctx is cancelled.
func (c *Consumer) Run(ctx context.Context) {
	for ctx.Err() == nil {
		if err := c.PollOnce(ctx); err != nil && ctx.Err() == nil {
			c.log.Error().Err(err).Msg("receive failed")
			select {
			case <-ctx.Done():
			case <-time.After(2 * time.Second):
			}
		}
	}
}

// PollOnce receives up to 10 messages, enqueues deliveries, and deletes the
// messages that were handled (successfully or as unparseable poison).
func (c *Consumer) PollOnce(ctx context.Context) error {
	out, err := c.sqs.ReceiveMessage(ctx, &sqs.ReceiveMessageInput{
		QueueUrl:              aws.String(c.queueURL),
		MaxNumberOfMessages:   10,
		WaitTimeSeconds:       c.wait,
		MessageAttributeNames: []string{"All"},
	})
	if err != nil {
		return err
	}
	for _, m := range out.Messages {
		c.handle(ctx, m)
	}
	return nil
}

func (c *Consumer) handle(ctx context.Context, m types.Message) {
	body := aws.ToString(m.Body)
	ev, err := events.Parse([]byte(body))
	if err != nil {
		// Unparseable messages will never succeed; drop them rather than block the queue.
		c.log.Warn().Err(err).Str("message_id", aws.ToString(m.MessageId)).Msg("dropping unrecognised message")
		c.delete(ctx, m)
		return
	}
	n, err := c.enq.Enqueue(ctx, ev)
	if err != nil {
		// Leave the message on the queue; visibility timeout will redeliver it and
		// the unique (subscription_id, event_id) index makes that safe.
		c.log.Error().Err(err).Str("event_id", ev.ID).Msg("enqueue failed; message left for redelivery")
		return
	}
	c.log.Info().Str("event_id", ev.ID).Str("event_type", ev.Type).Int("deliveries", n).Msg("event fanned out")
	c.delete(ctx, m)
}

func (c *Consumer) delete(ctx context.Context, m types.Message) {
	if _, err := c.sqs.DeleteMessage(ctx, &sqs.DeleteMessageInput{QueueUrl: aws.String(c.queueURL), ReceiptHandle: m.ReceiptHandle}); err != nil {
		c.log.Error().Err(err).Msg("delete message failed")
	}
}

// DLQ publishes dead-lettered deliveries onto an SQS dead-letter queue in
// addition to the dead_letter row kept in the database.
type DLQ struct {
	sqs      SQSAPI
	queueURL string
}

// NewDLQ returns nil when no queue URL is configured.
func NewDLQ(client SQSAPI, queueURL string) *DLQ {
	if queueURL == "" || client == nil {
		return nil
	}
	return &DLQ{sqs: client, queueURL: queueURL}
}

// Publish sends a compact record of the failed delivery.
func (q *DLQ) Publish(ctx context.Context, d *store.Delivery) error {
	if q == nil {
		return errors.New("dlq not configured")
	}
	body, err := json.Marshal(map[string]any{
		"deliveryId":     d.ID,
		"subscriptionId": d.SubscriptionID,
		"ownerId":        d.OwnerID,
		"eventId":        d.EventID,
		"eventType":      d.EventType,
		"attempts":       d.Attempts,
		"lastError":      d.LastError,
		"lastStatusCode": d.LastStatusCode,
		"payload":        json.RawMessage(d.Payload),
		"deadLetteredAt": time.Now().UTC(),
	})
	if err != nil {
		return err
	}
	_, err = q.sqs.SendMessage(ctx, &sqs.SendMessageInput{QueueUrl: aws.String(q.queueURL), MessageBody: aws.String(string(body))})
	return err
}
