package main

import (
	"encoding/json"
	"io"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"
)

type received struct {
	ReceivedAt     time.Time         `json:"received_at"`
	Event          string            `json:"event"`
	DeliveryID     string            `json:"delivery_id"`
	Timestamp      string            `json:"timestamp"`
	SignatureValid *bool             `json:"signature_valid"`
	Reason         *string           `json:"reason,omitempty"`
	Headers        map[string]string `json:"headers"`
	Body           json.RawMessage   `json:"body"`
}
type sink struct {
	mu       sync.Mutex
	items    []received
	failMode bool
	secret   string
}

func (s *sink) record(w http.ResponseWriter, r *http.Request) {
	body, err := readBody(r)
	if err != nil {
		jsonResponse(w, 400, map[string]string{"error": "invalid body"})
		return
	}
	headers := map[string]string{"event": r.Header.Get("X-OtterWorks-Event"), "delivery_id": r.Header.Get("X-OtterWorks-Delivery-Id"), "timestamp": r.Header.Get("X-OtterWorks-Timestamp"), "signature": r.Header.Get("X-OtterWorks-Signature")}
	var valid *bool
	var reason *string
	if s.secret != "" {
		value := false
		timestamp, parseErr := strconv.ParseInt(headers["timestamp"], 10, 64)
		if parseErr != nil || timestamp <= 0 {
			message := "invalid timestamp"
			reason = &message
		} else if abs(time.Now().Unix()-timestamp) > 300 {
			message := "timestamp outside five minute tolerance"
			reason = &message
		} else {
			value = verify(s.secret, timestamp, body, headers["signature"])
			if !value {
				message := "invalid signature"
				reason = &message
			}
		}
		valid = &value
	} else {
		log.Printf(`{"message":"unverified","delivery_id":%q}`, headers["delivery_id"])
	}
	item := received{ReceivedAt: time.Now().UTC(), Event: headers["event"], DeliveryID: headers["delivery_id"], Timestamp: headers["timestamp"], SignatureValid: valid, Reason: reason, Headers: headers, Body: json.RawMessage(body)}
	s.mu.Lock()
	s.items = append(s.items, item)
	if len(s.items) > 500 {
		s.items = s.items[len(s.items)-500:]
	}
	s.mu.Unlock()
	log.Printf(`{"delivery_id":%q,"event":%q,"signature_valid":%v}`, item.DeliveryID, item.Event, valid)
	if s.failMode {
		jsonResponse(w, 500, map[string]string{"error": "fail mode"})
		return
	}
	jsonResponse(w, 200, map[string]string{"status": "received"})
}
func (s *sink) received(w http.ResponseWriter, _ *http.Request) {
	s.mu.Lock()
	defer s.mu.Unlock()
	jsonResponse(w, 200, map[string]any{"count": len(s.items), "fail_mode": s.failMode, "items": s.items})
}
func health(w http.ResponseWriter, _ *http.Request) {
	jsonResponse(w, 200, map[string]string{"status": "healthy"})
}
func readBody(r *http.Request) ([]byte, error) {
	defer r.Body.Close()
	var body []byte
	buf := make([]byte, 1024*1024)
	for {
		n, err := r.Body.Read(buf)
		body = append(body, buf[:n]...)
		if err != nil {
			if err == io.EOF {
				return body, nil
			}
			return nil, err
		}
	}
}
func jsonResponse(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
func abs(value int64) int64 {
	if value < 0 {
		return -value
	}
	return value
}
func main() {
	s := &sink{failMode: parseBool(os.Getenv("FAIL_MODE")), secret: os.Getenv("WEBHOOK_SECRET")}
	mux := http.NewServeMux()
	mux.HandleFunc("/health", health)
	mux.HandleFunc("/received", s.received)
	mux.HandleFunc("/", s.record)
	port := os.Getenv("PORT")
	if port == "" {
		port = "8093"
	}
	log.Printf(`{"service":"webhook-sink","port":%q}`, port)
	if err := http.ListenAndServe(":"+port, mux); err != nil {
		log.Fatal(err)
	}
}
func parseBool(value string) bool { return value == "1" || strings.EqualFold(value, "true") }
