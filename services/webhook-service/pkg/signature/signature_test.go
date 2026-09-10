package signature

import "testing"

func TestRoundTrip(t *testing.T) {
	body := []byte(`{"event":"webhook.ping"}`)
	header := Sign("secret", 1700000000, body)
	if !Verify("secret", 1700000000, body, header) {
		t.Fatal("signature did not verify")
	}
	if Verify("wrong", 1700000000, body, header) {
		t.Fatal("wrong secret verified")
	}
}
