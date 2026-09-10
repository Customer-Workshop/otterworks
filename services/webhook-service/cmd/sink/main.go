// Command sink is a headless demo receiver for webhook deliveries. It verifies
// the HMAC signature of every POST, records what it received, and exposes the
// log as JSON so an end-to-end run can be asserted from the shell.
//
//	POST /hook    -> 200 after verifying the signature
//	POST /flaky   -> 503 for the first two attempts of each delivery, then 200
//	POST /fail    -> 500 always (drives the dead-letter path)
//	GET  /received -> JSON log of every request seen
//	GET  /health
package main

import (
	"encoding/json"
	"io"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/rs/zerolog"

	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/signing"
)

type received struct {
	Path       string          `json:"path"`
	ReceivedAt time.Time       `json:"receivedAt"`
	DeliveryID string          `json:"deliveryId"`
	EventID    string          `json:"eventId"`
	EventType  string          `json:"eventType"`
	Verified   bool            `json:"signatureVerified"`
	Status     int             `json:"respondedWith"`
	Body       json.RawMessage `json:"body"`
}

type sink struct {
	secret string
	log    zerolog.Logger

	mu    sync.Mutex
	seen  []received
	flaky map[string]int
}

func main() {
	log := zerolog.New(os.Stdout).With().Timestamp().Str("service", "webhook-sink").Logger()
	port := os.Getenv("PORT")
	if port == "" {
		port = "8093"
	}
	s := &sink{secret: os.Getenv("SINK_SECRET"), log: log, flaky: map[string]int{}}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) { writeJSON(w, 200, map[string]string{"status": "ok"}) })
	mux.HandleFunc("/received", s.list)
	mux.HandleFunc("/hook", s.handle(func(string) int { return 200 }))
	mux.HandleFunc("/fail", s.handle(func(string) int { return 500 }))
	mux.HandleFunc("/flaky", s.handle(func(id string) int {
		s.mu.Lock()
		defer s.mu.Unlock()
		s.flaky[id]++
		if s.flaky[id] <= 2 {
			return 503
		}
		return 200
	}))
	mux.HandleFunc("/", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, 404, map[string]string{"error": "not found"})
	})

	log.Info().Str("port", port).Msg("webhook sink listening")
	if err := (&http.Server{Addr: ":" + port, Handler: mux, ReadHeaderTimeout: 5 * time.Second}).ListenAndServe(); err != nil {
		log.Fatal().Err(err).Msg("sink stopped")
	}
}

func (s *sink) handle(status func(deliveryID string) int) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeJSON(w, 405, map[string]string{"error": "method not allowed"})
			return
		}
		body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
		if err != nil {
			writeJSON(w, 400, map[string]string{"error": "read body"})
			return
		}
		rec := received{
			Path: r.URL.Path, ReceivedAt: time.Now().UTC(),
			DeliveryID: r.Header.Get(signing.HeaderDeliveryID),
			EventID:    r.Header.Get(signing.HeaderEventID),
			EventType:  r.Header.Get(signing.HeaderEvent),
			Body:       body,
		}
		if !json.Valid(body) {
			rec.Body = json.RawMessage(`null`)
		}
		verr := signing.Verify(s.secret, r.Header.Get(signing.HeaderSignature), body, time.Now(), 5*time.Minute)
		rec.Verified = verr == nil
		switch {
		case s.secret == "":
			rec.Status = 500
		case !rec.Verified:
			rec.Status = 401
		default:
			rec.Status = status(rec.DeliveryID)
		}
		s.mu.Lock()
		s.seen = append(s.seen, rec)
		s.mu.Unlock()
		s.log.Info().Str("path", rec.Path).Str("delivery_id", rec.DeliveryID).Str("event_type", rec.EventType).Bool("verified", rec.Verified).Int("status", rec.Status).Msg("delivery received")
		writeJSON(w, rec.Status, map[string]any{"received": true, "signatureVerified": rec.Verified, "deliveryId": rec.DeliveryID})
	}
}

func (s *sink) list(w http.ResponseWriter, r *http.Request) {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]received, 0, len(s.seen))
	filter := r.URL.Query().Get("deliveryId")
	for _, rec := range s.seen {
		if filter == "" || rec.DeliveryID == filter {
			out = append(out, rec)
		}
	}
	writeJSON(w, 200, map[string]any{"count": len(out), "received": out})
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}
