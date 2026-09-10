package delivery

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"time"

	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/store"
	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/pkg/signature"
	"github.com/google/uuid"
	"github.com/rs/zerolog"
)

type Worker struct {
	store        store.Store
	client       *http.Client
	pollInterval time.Duration
	baseBackoff  time.Duration
	logger       zerolog.Logger
	now          func() time.Time
}

func NewWorker(s store.Store, client *http.Client, pollInterval, baseBackoff time.Duration, logger zerolog.Logger) *Worker {
	if client == nil {
		client = &http.Client{Timeout: 5 * time.Second}
	}
	return &Worker{store: s, client: client, pollInterval: pollInterval, baseBackoff: baseBackoff, logger: logger, now: func() time.Time { return time.Now().UTC() }}
}
func (w *Worker) Run(ctx context.Context) {
	ticker := time.NewTicker(w.pollInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			w.Process(ctx)
		}
	}
}
func (w *Worker) Process(ctx context.Context) {
	deliveries, err := w.store.ClaimDueDeliveries(ctx, 20)
	if err != nil {
		w.logger.Error().Err(err).Msg("claim webhook deliveries")
		return
	}
	for _, d := range deliveries {
		if err := w.deliver(ctx, d); err != nil {
			w.logger.Warn().Err(err).Str("delivery_id", d.ID.String()).Msg("webhook delivery failed")
		}
	}
}
func (w *Worker) deliver(ctx context.Context, d store.Delivery) error {
	now := w.now()
	payload := map[string]any{"id": d.ID, "event": d.EventType, "created_at": d.CreatedAt, "data": json.RawMessage(d.Payload)}
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	ts := now.Unix()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, d.TargetURL, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", "OtterWorks-Webhooks/0.1")
	req.Header.Set("X-OtterWorks-Event", d.EventType)
	req.Header.Set("X-OtterWorks-Delivery-Id", d.ID.String())
	req.Header.Set("X-OtterWorks-Timestamp", strconv.FormatInt(ts, 10))
	req.Header.Set("X-OtterWorks-Signature", signature.Sign(d.Secret, ts, body))
	start := time.Now()
	resp, requestErr := w.client.Do(req)
	duration := int(time.Since(start).Milliseconds())
	var responseCode *int
	var lastError *string
	if requestErr != nil {
		msg := requestErr.Error()
		lastError = &msg
	} else {
		responseCode = &resp.StatusCode
		_, _ = io.Copy(io.Discard, resp.Body)
		resp.Body.Close()
		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			msg := fmt.Sprintf("partner returned HTTP %d", resp.StatusCode)
			lastError = &msg
		}
	}
	attempt := d.Attempts + 1
	a := &store.DeliveryAttempt{ID: uuid.New(), DeliveryID: d.ID, Attempt: attempt, ResponseCode: responseCode, Error: lastError, DurationMS: duration, AttemptedAt: now}
	if err := w.store.RecordAttempt(ctx, a); err != nil {
		return err
	}
	if lastError == nil {
		return w.store.MarkDelivered(ctx, d.ID, now)
	}
	if attempt < d.MaxAttempts {
		return w.store.MarkRetry(ctx, d.ID, now.Add(w.baseBackoff*time.Duration(1<<(attempt-1))))
	}
	return w.store.MarkFailed(ctx, d.ID)
}
