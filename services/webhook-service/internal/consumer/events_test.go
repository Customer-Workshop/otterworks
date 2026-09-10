package consumer

import (
	"testing"
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
