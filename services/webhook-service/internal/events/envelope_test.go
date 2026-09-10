package events

import (
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestParseSNSEnvelopeWithFileServiceMessage(t *testing.T) {
	inner := `{"eventType":"file_uploaded","fileId":"f1","ownerId":"u1","timestamp":"2026-01-02T03:04:05Z","name":"a.txt"}`
	env, _ := json.Marshal(map[string]string{
		"Type": "Notification", "MessageId": "msg-123", "Message": inner, "Timestamp": "2026-01-02T03:04:06.000Z",
	})
	ev, err := Parse(env)
	require.NoError(t, err)
	assert.Equal(t, "msg-123", ev.ID)
	assert.Equal(t, "file_uploaded", ev.Type)
	assert.Equal(t, "file-service", ev.Source)
	assert.Equal(t, "2026-01-02T03:04:05Z", ev.OccurredAt.Format("2006-01-02T15:04:05Z"))
	assert.JSONEq(t, inner, string(ev.Data))
}

func TestParseDocumentServiceMessage(t *testing.T) {
	body := `{"event_type":"document_created","timestamp":"2026-01-02T03:04:05+00:00","payload":{"id":"d1","title":"Plan"}}`
	ev, err := Parse([]byte(body))
	require.NoError(t, err)
	assert.Equal(t, "document_created", ev.Type)
	assert.Equal(t, "document-service", ev.Source)
	assert.JSONEq(t, `{"id":"d1","title":"Plan"}`, string(ev.Data))
	assert.Regexp(t, `^evt_[0-9a-f]{32}$`, ev.ID)

	again, err := Parse([]byte(body))
	require.NoError(t, err)
	assert.Equal(t, ev.ID, again.ID, "fallback ID must be deterministic for dedupe")
}

func TestParseRejectsUnknownShapes(t *testing.T) {
	_, err := Parse([]byte(`{"hello":"world"}`))
	assert.ErrorIs(t, err, ErrUnrecognised)
	_, err = Parse([]byte(`not json`))
	assert.Error(t, err)
	_, err = Parse([]byte(`{"eventType":"  "}`))
	assert.ErrorIs(t, err, ErrUnrecognised)
}
