package signing

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestSignVerifyRoundTrip(t *testing.T) {
	secret, err := NewSecret()
	require.NoError(t, err)
	assert.Contains(t, secret, "whsec_")

	body := []byte(`{"eventType":"file_uploaded"}`)
	now := time.Unix(1700000000, 0)
	header := Sign(secret, now, body)
	assert.Regexp(t, `^t=1700000000,v1=[0-9a-f]{64}$`, header)

	require.NoError(t, Verify(secret, header, body, now.Add(2*time.Minute), 5*time.Minute))
	assert.Error(t, Verify(secret, header, []byte(`{"tampered":true}`), now, 5*time.Minute), "body tamper")
	assert.Error(t, Verify("whsec_other", header, body, now, 5*time.Minute), "wrong secret")
	assert.Error(t, Verify(secret, header, body, now.Add(time.Hour), 5*time.Minute), "replay outside tolerance")
	assert.Error(t, Verify(secret, "garbage", body, now, 0))
}

func TestSignIsDeterministic(t *testing.T) {
	now := time.Unix(1, 0)
	assert.Equal(t, Sign("s", now, []byte("a")), Sign("s", now, []byte("a")))
	assert.NotEqual(t, Sign("s", now, []byte("a")), Sign("s", now.Add(time.Second), []byte("a")))
}
