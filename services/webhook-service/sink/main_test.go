package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestVerify(t *testing.T) {
	body := []byte(`{"id":"1"}`)
	timestamp := time.Now().Unix()
	header := sign("secret", timestamp, body)
	if !verify("secret", timestamp, body, header) {
		t.Fatal("signature should verify with same timestamp")
	}
}
func TestFailModeRecordsAndReturns500(t *testing.T) {
	s := &sink{failMode: true}
	server := httptest.NewServer(http.HandlerFunc(s.record))
	defer server.Close()
	response, err := http.Post(server.URL, "application/json", strings.NewReader(`{"event":"webhook.ping"}`))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != 500 {
		t.Fatalf("status=%d", response.StatusCode)
	}
	if _, err := io.ReadAll(response.Body); err != nil {
		t.Fatal(err)
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if len(s.items) != 1 {
		t.Fatalf("items=%d", len(s.items))
	}
}
