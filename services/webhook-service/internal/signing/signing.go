// Package signing implements the HMAC-SHA256 scheme used on every outbound
// webhook. Receivers verify with:
//
//	expected = hex(HMAC_SHA256(secret, "<timestamp>.<raw body>"))
//	header   = "t=<timestamp>,v1=<expected>"
package signing

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"
)

// Header names sent with every delivery.
const (
	HeaderSignature  = "X-OtterWorks-Signature"
	HeaderEvent      = "X-OtterWorks-Event"
	HeaderDeliveryID = "X-OtterWorks-Delivery-ID"
	HeaderEventID    = "X-OtterWorks-Event-ID"
	HeaderTimestamp  = "X-OtterWorks-Timestamp"
)

// NewSecret returns a random 32-byte secret, hex encoded, prefixed for recognisability.
func NewSecret() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return "whsec_" + hex.EncodeToString(b), nil
}

// Sign computes the signature header value for body at timestamp ts.
func Sign(secret string, ts time.Time, body []byte) string {
	unix := strconv.FormatInt(ts.Unix(), 10)
	return "t=" + unix + ",v1=" + digest(secret, unix, body)
}

func digest(secret, unixTs string, body []byte) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(unixTs))
	mac.Write([]byte("."))
	mac.Write(body)
	return hex.EncodeToString(mac.Sum(nil))
}

// Verify checks header against body using secret, rejecting signatures whose
// timestamp is further than tolerance from now (replay protection).
func Verify(secret, header string, body []byte, now time.Time, tolerance time.Duration) error {
	var ts, sig string
	for _, part := range strings.Split(header, ",") {
		kv := strings.SplitN(strings.TrimSpace(part), "=", 2)
		if len(kv) != 2 {
			continue
		}
		switch kv[0] {
		case "t":
			ts = kv[1]
		case "v1":
			sig = kv[1]
		}
	}
	if ts == "" || sig == "" {
		return errors.New("signature header missing t or v1")
	}
	unix, err := strconv.ParseInt(ts, 10, 64)
	if err != nil {
		return fmt.Errorf("invalid timestamp: %w", err)
	}
	if tolerance > 0 {
		delta := now.Sub(time.Unix(unix, 0))
		if delta < 0 {
			delta = -delta
		}
		if delta > tolerance {
			return errors.New("signature timestamp outside tolerance")
		}
	}
	if !hmac.Equal([]byte(sig), []byte(digest(secret, ts, body))) {
		return errors.New("signature mismatch")
	}
	return nil
}
