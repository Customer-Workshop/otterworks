package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"strconv"
	"strings"
)

func sign(secret string, timestamp int64, body []byte) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(strconv.FormatInt(timestamp, 10) + "."))
	mac.Write(body)
	return "sha256=" + hex.EncodeToString(mac.Sum(nil))
}
func verify(secret string, timestamp int64, body []byte, header string) bool {
	return hmac.Equal([]byte(sign(secret, timestamp, body)), []byte(strings.TrimSpace(header)))
}
