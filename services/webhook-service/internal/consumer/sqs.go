package consumer

import (
	"context"
	"encoding/json"
	"time"

	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/store"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/google/uuid"
	"github.com/rs/zerolog"
)

type Consumer struct {
	client      *sqs.Client
	queueURL    string
	store       store.Store
	logger      zerolog.Logger
	wait        int32
	maxAttempts int
}

func New(client *sqs.Client, queueURL string, s store.Store, logger zerolog.Logger, wait int32, maxAttempts ...int) *Consumer {
	attempts := 5
	if len(maxAttempts) > 0 && maxAttempts[0] > 0 {
		attempts = maxAttempts[0]
	}
	return &Consumer{client: client, queueURL: queueURL, store: s, logger: logger, wait: wait, maxAttempts: attempts}
}
func (c *Consumer) Run(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}
		output, err := c.client.ReceiveMessage(ctx, &sqs.ReceiveMessageInput{QueueUrl: &c.queueURL, WaitTimeSeconds: c.wait, MaxNumberOfMessages: 10})
		if err != nil {
			c.logger.Error().Err(err).Msg("receive SQS messages")
			time.Sleep(time.Second)
			continue
		}
		for _, message := range output.Messages {
			if message.Body == nil || *message.Body == "" {
				c.delete(ctx, message.ReceiptHandle)
				continue
			}
			event, err := ParseMessage(*message.Body)
			if err != nil {
				c.logger.Warn().Err(err).Msg("could not parse event")
			} else if event != nil {
				c.enqueue(ctx, event)
			}
			c.delete(ctx, message.ReceiptHandle)
		}
	}
}
func (c *Consumer) enqueue(ctx context.Context, event *ParsedEvent) {
	subs, err := c.store.ListActiveSubscriptionsForEvent(ctx, event.WebhookType)
	if err != nil {
		c.logger.Error().Err(err).Msg("list webhook subscriptions")
		return
	}
	payload, _ := json.Marshal(map[string]any{"event": event.WebhookType, "source_event_type": event.BusType, "occurred_at": event.OccurredAt, "data": event.Data})
	for _, sub := range subs {
		now := time.Now().UTC()
		if err := c.store.EnqueueDelivery(ctx, &store.Delivery{ID: uuid.New(), SubscriptionID: sub.ID, EventType: event.WebhookType, Payload: payload, Status: "pending", MaxAttempts: c.maxAttempts, NextAttemptAt: now, CreatedAt: now, UpdatedAt: now}); err != nil {
			c.logger.Error().Err(err).Msg("enqueue webhook delivery")
		}
	}
}
func (c *Consumer) delete(ctx context.Context, receipt *string) {
	if receipt == nil {
		return
	}
	_, err := c.client.DeleteMessage(ctx, &sqs.DeleteMessageInput{QueueUrl: &c.queueURL, ReceiptHandle: receipt})
	if err != nil {
		c.logger.Warn().Err(err).Msg("delete SQS message")
	}
}
