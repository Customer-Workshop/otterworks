// Package events normalises the messages that arrive on the webhook SQS queue
// from the otterworks-events SNS topic. Producers do not share a schema:
// file-service (Rust) emits camelCase {"eventType","fileId",...}, while
// document-service (Python) emits {"event_type","timestamp","payload":{...}}.
package events

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"
)

// Event is the normalised shape delivered to webhook receivers.
type Event struct {
	ID         string          `json:"id"`
	Type       string          `json:"type"`
	Source     string          `json:"source"`
	OccurredAt time.Time       `json:"occurredAt"`
	Data       json.RawMessage `json:"data"`
}

// snsEnvelope is the wrapper SNS puts around a message when fanning out to SQS.
type snsEnvelope struct {
	Type      string `json:"Type"`
	MessageID string `json:"MessageId"`
	Message   string `json:"Message"`
	Timestamp string `json:"Timestamp"`
}

// ErrUnrecognised means the body carried no event type we can route on.
var ErrUnrecognised = errors.New("message has no recognised event type")

// Parse accepts either a raw SNS envelope (as read from SQS) or a bare
// producer message and returns the normalised event.
func Parse(body []byte) (*Event, error) {
	var env snsEnvelope
	if err := json.Unmarshal(body, &env); err == nil && env.Type == "Notification" && env.Message != "" {
		ev, err := parseProducerMessage([]byte(env.Message))
		if err != nil {
			return nil, err
		}
		if env.MessageID != "" {
			ev.ID = env.MessageID
		}
		if ev.OccurredAt.IsZero() && env.Timestamp != "" {
			if t, err := time.Parse(time.RFC3339Nano, env.Timestamp); err == nil {
				ev.OccurredAt = t
			}
		}
		return ev, nil
	}
	return parseProducerMessage(body)
}

func parseProducerMessage(body []byte) (*Event, error) {
	var generic map[string]json.RawMessage
	if err := json.Unmarshal(body, &generic); err != nil {
		return nil, err
	}
	ev := &Event{}

	switch {
	case generic["event_type"] != nil:
		// document-service shape
		_ = json.Unmarshal(generic["event_type"], &ev.Type)
		if p, ok := generic["payload"]; ok {
			ev.Data = p
		} else {
			ev.Data = body
		}
		ev.Source = "document-service"
	case generic["eventType"] != nil:
		// file-service shape: the whole message is the data
		_ = json.Unmarshal(generic["eventType"], &ev.Type)
		ev.Data = body
		ev.Source = "file-service"
	default:
		return nil, ErrUnrecognised
	}
	ev.Type = strings.TrimSpace(ev.Type)
	if ev.Type == "" {
		return nil, ErrUnrecognised
	}
	if ts, ok := generic["timestamp"]; ok {
		var s string
		if json.Unmarshal(ts, &s) == nil {
			if t, err := time.Parse(time.RFC3339Nano, s); err == nil {
				ev.OccurredAt = t
			}
		}
	}
	if ev.OccurredAt.IsZero() {
		ev.OccurredAt = time.Now().UTC()
	}
	// Deterministic fallback ID so redelivered messages dedupe even without an SNS MessageId.
	sum := sha256.Sum256(body)
	ev.ID = "evt_" + hex.EncodeToString(sum[:16])
	return ev, nil
}
