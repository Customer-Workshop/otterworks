package consumer

import (
	"encoding/json"
	"fmt"
	"time"
)

type ParsedEvent struct {
	BusType     string
	WebhookType string
	OccurredAt  time.Time
	Data        any
	MessageID   string
}

var eventMapping = map[string]string{"file_shared": "file.shared", "document_updated": "document.updated", "comment_added": "comment.added"}

func ParseMessage(body string) (*ParsedEvent, error) {
	return ParseMessageWithID(body, "")
}

func ParseMessageWithID(body, fallbackMessageID string) (*ParsedEvent, error) {
	var raw map[string]any
	if err := json.Unmarshal([]byte(body), &raw); err != nil {
		return nil, fmt.Errorf("invalid message: %w", err)
	}
	inner := []byte(body)
	messageID := fallbackMessageID
	if wrapperID, ok := raw["MessageId"].(string); ok && wrapperID != "" {
		messageID = wrapperID
	}
	if message, ok := raw["Message"].(string); ok && message != "" {
		inner = []byte(message)
	}
	var event map[string]any
	if err := json.Unmarshal(inner, &event); err != nil {
		return nil, fmt.Errorf("invalid event: %w", err)
	}
	busType := stringValue(event, "event_type", "eventType")
	webhookType, ok := eventMapping[busType]
	if !ok {
		return nil, nil
	}
	occurred := time.Now().UTC()
	if timestamp, ok := event["timestamp"].(string); ok {
		if parsed, err := time.Parse(time.RFC3339, timestamp); err == nil {
			occurred = parsed
		}
	}
	data := make(map[string]any)
	if payload, ok := event["payload"].(map[string]any); ok {
		data = payload
	} else {
		for key, value := range event {
			if key != "event_type" && key != "eventType" && key != "timestamp" {
				data[key] = value
			}
		}
	}
	return &ParsedEvent{BusType: busType, WebhookType: webhookType, OccurredAt: occurred, Data: data, MessageID: messageID}, nil
}

func stringValue(event map[string]any, keys ...string) string {
	for _, key := range keys {
		if value, ok := event[key].(string); ok {
			return value
		}
	}
	return ""
}
