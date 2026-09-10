// Package api exposes the JSON-only HTTP surface of the webhook service.
// Every response — including errors, 404s and 405s — is application/json.
package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/google/uuid"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/rs/zerolog"

	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/dispatch"
	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/signing"
	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/store"
)

// KnownEventTypes are the events published on the otterworks-events topic today.
var KnownEventTypes = []string{
	"file_uploaded", "file_deleted", "file_shared", "file_trashed", "file_restored", "file_updated", "file_moved",
	"document_created", "document_updated", "document_deleted",
	"comment_added",
}

const (
	// HeaderUserID is set by the API gateway from the validated JWT subject.
	HeaderUserID = "X-User-ID"
	maxBody      = 64 << 10
	maxPageSize  = 200
	// minSecretLen matches the 256-bit key HMAC-SHA256 expects; anything shorter
	// lets a receiver's signature check be brute-forced offline.
	minSecretLen = 32
	// maxOwnerIDLen bounds the identity the gateway forwards; JWT subjects are
	// UUIDs or short opaque ids, never free text.
	maxOwnerIDLen = 128
)

// Options configures the API.
type Options struct {
	MaxAttempts         int
	AllowPrivateTargets bool
	// Readiness reports whether backing services are reachable.
	Readiness func(ctx context.Context) error
}

// Server holds handlers.
type Server struct {
	store store.Store
	opts  Options
	log   zerolog.Logger
	now   func() time.Time
}

// New returns the service router.
func New(st store.Store, opts Options, log zerolog.Logger) http.Handler {
	s := &Server{store: st, opts: opts, log: log, now: func() time.Time { return time.Now().UTC() }}
	r := chi.NewRouter()
	r.Use(middleware.RequestID, middleware.RealIP, middleware.Recoverer, jsonOnly)
	r.NotFound(func(w http.ResponseWriter, r *http.Request) {
		writeError(w, http.StatusNotFound, "not_found", "route not found")
	})
	r.MethodNotAllowed(func(w http.ResponseWriter, r *http.Request) {
		writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
	})

	r.Get("/health", s.health)
	r.Get("/ready", s.ready)
	r.Handle("/metrics", promhttp.Handler())

	r.Route("/api/v1/webhooks", func(r chi.Router) {
		r.Use(s.requireOwner)
		r.Get("/", s.index)
		r.Get("/event-types", s.eventTypes)
		r.Get("/stats", s.stats)

		r.Route("/subscriptions", func(r chi.Router) {
			r.Get("/", s.listSubscriptions)
			r.Post("/", s.createSubscription)
			r.Route("/{id}", func(r chi.Router) {
				r.Use(requireUUID)
				r.Get("/", s.getSubscription)
				r.Put("/", s.updateSubscription)
				r.Patch("/", s.updateSubscription)
				r.Delete("/", s.deleteSubscription)
				r.Post("/rotate-secret", s.rotateSecret)
				r.Post("/test", s.testSubscription)
			})
		})
		r.Route("/deliveries", func(r chi.Router) {
			r.Get("/", s.listDeliveries)
			r.Route("/{id}", func(r chi.Router) {
				r.Use(requireUUID)
				r.Get("/", s.getDelivery)
				r.Get("/attempts", s.listAttempts)
				r.Post("/replay", s.replayDelivery)
			})
		})
		r.Get("/dead-letters", s.listDeadLetters)
	})
	return r
}

// jsonOnly forces the content type before any handler writes.
func jsonOnly(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Cache-Control", "no-store")
		next.ServeHTTP(w, r)
	})
}

type errorBody struct {
	Error   string `json:"error"`
	Message string `json:"message"`
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, code, msg string) {
	writeJSON(w, status, errorBody{Error: code, Message: msg})
}

func (s *Server) storeErr(w http.ResponseWriter, err error) {
	if errors.Is(err, store.ErrNotFound) {
		writeError(w, http.StatusNotFound, "not_found", "resource not found")
		return
	}
	if errors.Is(err, store.ErrConflict) {
		writeError(w, http.StatusConflict, "conflict", "only dead_letter deliveries can be replayed")
		return
	}
	s.log.Error().Err(err).Msg("store error")
	writeError(w, http.StatusInternalServerError, "internal_error", "internal error")
}

// requireUUID answers 404 for malformed ids so the store never sees a value
// Postgres would reject with a type error.
func requireUUID(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if _, err := uuid.Parse(chi.URLParam(r, "id")); err != nil {
			writeError(w, http.StatusNotFound, "not_found", "resource not found")
			return
		}
		next.ServeHTTP(w, r)
	})
}

type ctxKey int

const ownerKey ctxKey = iota

func (s *Server) requireOwner(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		owner := strings.TrimSpace(r.Header.Get(HeaderUserID))
		if owner == "" {
			writeError(w, http.StatusUnauthorized, "unauthorized", "missing authenticated user; requests must come through the API gateway")
			return
		}
		if !validOwnerID(owner) {
			writeError(w, http.StatusUnauthorized, "unauthorized", "malformed authenticated user identity")
			return
		}
		next.ServeHTTP(w, r.WithContext(context.WithValue(r.Context(), ownerKey, owner)))
	})
}

// validOwnerID accepts only bounded, printable, whitespace-free ASCII so a
// forwarded identity can never smuggle control characters or oversized keys
// into owner-scoped storage.
func validOwnerID(id string) bool {
	if len(id) > maxOwnerIDLen {
		return false
	}
	for i := 0; i < len(id); i++ {
		if id[i] <= ' ' || id[i] > '~' {
			return false
		}
	}
	return true
}

func owner(r *http.Request) string { v, _ := r.Context().Value(ownerKey).(string); return v }

func decode(r *http.Request, v any) error {
	ct := r.Header.Get("Content-Type")
	if ct != "" && !strings.HasPrefix(ct, "application/json") {
		return errors.New("Content-Type must be application/json")
	}
	dec := json.NewDecoder(http.MaxBytesReader(nil, r.Body, maxBody))
	dec.DisallowUnknownFields()
	if err := dec.Decode(v); err != nil {
		return err
	}
	return nil
}

// --- health ---------------------------------------------------------------

func (s *Server) health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "healthy", "service": "webhook-service", "headless": true})
}

func (s *Server) ready(w http.ResponseWriter, r *http.Request) {
	if s.opts.Readiness != nil {
		if err := s.opts.Readiness(r.Context()); err != nil {
			writeJSON(w, http.StatusServiceUnavailable, map[string]any{"status": "not_ready", "error": err.Error()})
			return
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ready"})
}

func (s *Server) index(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"service": "webhook-service",
		"resources": map[string]string{
			"subscriptions": "/api/v1/webhooks/subscriptions",
			"deliveries":    "/api/v1/webhooks/deliveries",
			"deadLetters":   "/api/v1/webhooks/dead-letters",
			"eventTypes":    "/api/v1/webhooks/event-types",
			"stats":         "/api/v1/webhooks/stats",
		},
		"signature": map[string]string{
			"header":    signing.HeaderSignature,
			"algorithm": "HMAC-SHA256",
			"format":    "t=<unix>,v1=hex(hmac(secret, \"<unix>.<raw-body>\"))",
		},
	})
}

func (s *Server) eventTypes(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"eventTypes": KnownEventTypes, "wildcard": "*"})
}

func (s *Server) stats(w http.ResponseWriter, r *http.Request) {
	st, err := s.store.Stats(r.Context(), owner(r))
	if err != nil {
		s.storeErr(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"deliveries": st})
}

// --- subscriptions --------------------------------------------------------

type subscriptionInput struct {
	URL         *string   `json:"url"`
	Description *string   `json:"description"`
	EventTypes  *[]string `json:"eventTypes"`
	Active      *bool     `json:"active"`
	Secret      *string   `json:"secret"`
}

type subscriptionCreated struct {
	*store.Subscription
	Secret string `json:"secret"`
}

func (s *Server) validateEventTypes(types []string) error {
	if len(types) == 0 {
		return errors.New("eventTypes must contain at least one entry (or \"*\")")
	}
	known := map[string]bool{"*": true}
	for _, k := range KnownEventTypes {
		known[k] = true
	}
	for _, t := range types {
		if !known[t] {
			return errors.New("unknown event type: " + t)
		}
	}
	return nil
}

func (s *Server) createSubscription(w http.ResponseWriter, r *http.Request) {
	var in subscriptionInput
	if err := decode(r, &in); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_json", err.Error())
		return
	}
	if in.URL == nil || *in.URL == "" {
		writeError(w, http.StatusBadRequest, "validation_error", "url is required")
		return
	}
	if err := dispatch.ValidateTargetURL(*in.URL, s.opts.AllowPrivateTargets); err != nil {
		writeError(w, http.StatusBadRequest, "validation_error", err.Error())
		return
	}
	if in.EventTypes == nil {
		writeError(w, http.StatusBadRequest, "validation_error", "eventTypes is required")
		return
	}
	if err := s.validateEventTypes(*in.EventTypes); err != nil {
		writeError(w, http.StatusBadRequest, "validation_error", err.Error())
		return
	}
	secret := ""
	if in.Secret != nil {
		if len(*in.Secret) < minSecretLen {
			writeError(w, http.StatusBadRequest, "validation_error", "secret must be at least 32 characters")
			return
		}
		secret = *in.Secret
	} else {
		var err error
		if secret, err = signing.NewSecret(); err != nil {
			s.storeErr(w, err)
			return
		}
	}
	now := s.now()
	sub := &store.Subscription{
		ID: uuid.NewString(), OwnerID: owner(r), URL: *in.URL, EventTypes: *in.EventTypes,
		Secret: secret, Active: true, CreatedAt: now, UpdatedAt: now,
	}
	if in.Description != nil {
		sub.Description = *in.Description
	}
	if in.Active != nil {
		sub.Active = *in.Active
	}
	if err := s.store.CreateSubscription(r.Context(), sub); err != nil {
		s.storeErr(w, err)
		return
	}
	// The secret is returned exactly once, at creation (and on rotation).
	writeJSON(w, http.StatusCreated, subscriptionCreated{Subscription: sub, Secret: secret})
}

func (s *Server) listSubscriptions(w http.ResponseWriter, r *http.Request) {
	subs, err := s.store.ListSubscriptions(r.Context(), owner(r))
	if err != nil {
		s.storeErr(w, err)
		return
	}
	if subs == nil {
		subs = []*store.Subscription{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"subscriptions": subs, "count": len(subs)})
}

func (s *Server) getSubscription(w http.ResponseWriter, r *http.Request) {
	sub, err := s.store.GetSubscription(r.Context(), owner(r), chi.URLParam(r, "id"))
	if err != nil {
		s.storeErr(w, err)
		return
	}
	writeJSON(w, http.StatusOK, sub)
}

func (s *Server) updateSubscription(w http.ResponseWriter, r *http.Request) {
	sub, err := s.store.GetSubscription(r.Context(), owner(r), chi.URLParam(r, "id"))
	if err != nil {
		s.storeErr(w, err)
		return
	}
	var in subscriptionInput
	if err := decode(r, &in); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_json", err.Error())
		return
	}
	if in.Secret != nil {
		writeError(w, http.StatusBadRequest, "validation_error", "use /rotate-secret to change the secret")
		return
	}
	if in.URL != nil {
		if err := dispatch.ValidateTargetURL(*in.URL, s.opts.AllowPrivateTargets); err != nil {
			writeError(w, http.StatusBadRequest, "validation_error", err.Error())
			return
		}
		sub.URL = *in.URL
	}
	if in.EventTypes != nil {
		if err := s.validateEventTypes(*in.EventTypes); err != nil {
			writeError(w, http.StatusBadRequest, "validation_error", err.Error())
			return
		}
		sub.EventTypes = *in.EventTypes
	}
	if in.Description != nil {
		sub.Description = *in.Description
	}
	if in.Active != nil {
		sub.Active = *in.Active
	}
	sub.UpdatedAt = s.now()
	if err := s.store.UpdateSubscription(r.Context(), sub); err != nil {
		s.storeErr(w, err)
		return
	}
	writeJSON(w, http.StatusOK, sub)
}

func (s *Server) deleteSubscription(w http.ResponseWriter, r *http.Request) {
	if err := s.store.DeleteSubscription(r.Context(), owner(r), chi.URLParam(r, "id")); err != nil {
		s.storeErr(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"deleted": true, "id": chi.URLParam(r, "id")})
}

func (s *Server) rotateSecret(w http.ResponseWriter, r *http.Request) {
	sub, err := s.store.GetSubscription(r.Context(), owner(r), chi.URLParam(r, "id"))
	if err != nil {
		s.storeErr(w, err)
		return
	}
	secret, err := signing.NewSecret()
	if err != nil {
		s.storeErr(w, err)
		return
	}
	sub.Secret = secret
	sub.UpdatedAt = s.now()
	if err := s.store.RotateSecret(r.Context(), sub.OwnerID, sub.ID, secret, sub.UpdatedAt); err != nil {
		s.storeErr(w, err)
		return
	}
	writeJSON(w, http.StatusOK, subscriptionCreated{Subscription: sub, Secret: secret})
}

// testSubscription enqueues a synthetic "webhook.test" delivery so users can
// verify their receiver + signature handling without waiting for a real event.
func (s *Server) testSubscription(w http.ResponseWriter, r *http.Request) {
	sub, err := s.store.GetSubscription(r.Context(), owner(r), chi.URLParam(r, "id"))
	if err != nil {
		s.storeErr(w, err)
		return
	}
	now := s.now()
	eventID := "test_" + uuid.NewString()
	payload, _ := json.Marshal(map[string]any{
		"id": eventID, "type": "webhook.test", "source": "webhook-service", "occurredAt": now,
		"data": map[string]any{"subscriptionId": sub.ID, "message": "test delivery"}, "subscriptionId": sub.ID,
	})
	d := &store.Delivery{
		ID: uuid.NewString(), SubscriptionID: sub.ID, OwnerID: sub.OwnerID, EventID: eventID, EventType: "webhook.test",
		Payload: payload, Status: store.StatusPending, MaxAttempts: s.opts.MaxAttempts, NextAttemptAt: &now,
		CreatedAt: now, UpdatedAt: now,
	}
	if d.MaxAttempts < 1 {
		d.MaxAttempts = 1
	}
	if err := s.store.CreateDeliveries(r.Context(), []*store.Delivery{d}); err != nil {
		s.storeErr(w, err)
		return
	}
	writeJSON(w, http.StatusAccepted, d)
}

// --- deliveries -----------------------------------------------------------

func (s *Server) filterFrom(r *http.Request) (store.DeliveryFilter, error) {
	q := r.URL.Query()
	f := store.DeliveryFilter{
		OwnerID:        owner(r),
		SubscriptionID: q.Get("subscriptionId"),
		EventType:      q.Get("eventType"),
		Status:         q.Get("status"),
		Cursor:         q.Get("cursor"),
		Limit:          50,
	}
	if f.SubscriptionID != "" {
		if _, err := uuid.Parse(f.SubscriptionID); err != nil {
			return f, errors.New("subscriptionId must be a UUID")
		}
	}
	if v := q.Get("limit"); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil || n < 1 || n > maxPageSize {
			return f, errors.New("limit must be an integer between 1 and " + strconv.Itoa(maxPageSize))
		}
		f.Limit = n
	}
	if v := q.Get("since"); v != "" {
		t, err := time.Parse(time.RFC3339, v)
		if err != nil {
			return f, errors.New("since must be RFC3339")
		}
		f.Since = &t
	}
	switch f.Status {
	case "", store.StatusPending, store.StatusRetrying, store.StatusDelivered, store.StatusDeadLetter:
	default:
		return f, errors.New("status must be one of pending, retrying, delivered, dead_letter")
	}
	return f, nil
}

func (s *Server) writeDeliveries(w http.ResponseWriter, r *http.Request, f store.DeliveryFilter) {
	items, next, err := s.store.ListDeliveries(r.Context(), f)
	if errors.Is(err, store.ErrInvalidCursor) {
		writeError(w, http.StatusBadRequest, "validation_error", "cursor is invalid")
		return
	}
	if err != nil {
		s.storeErr(w, err)
		return
	}
	if items == nil {
		items = []*store.Delivery{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"deliveries": items, "count": len(items), "nextCursor": next})
}

func (s *Server) listDeliveries(w http.ResponseWriter, r *http.Request) {
	f, err := s.filterFrom(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "validation_error", err.Error())
		return
	}
	s.writeDeliveries(w, r, f)
}

func (s *Server) listDeadLetters(w http.ResponseWriter, r *http.Request) {
	f, err := s.filterFrom(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "validation_error", err.Error())
		return
	}
	f.Status = store.StatusDeadLetter
	s.writeDeliveries(w, r, f)
}

func (s *Server) getDelivery(w http.ResponseWriter, r *http.Request) {
	d, err := s.store.GetDelivery(r.Context(), owner(r), chi.URLParam(r, "id"))
	if err != nil {
		s.storeErr(w, err)
		return
	}
	writeJSON(w, http.StatusOK, d)
}

func (s *Server) listAttempts(w http.ResponseWriter, r *http.Request) {
	d, err := s.store.GetDelivery(r.Context(), owner(r), chi.URLParam(r, "id"))
	if err != nil {
		s.storeErr(w, err)
		return
	}
	attempts, err := s.store.ListAttempts(r.Context(), d.ID)
	if err != nil {
		s.storeErr(w, err)
		return
	}
	if attempts == nil {
		attempts = []*store.Attempt{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"deliveryId": d.ID, "attempts": attempts, "count": len(attempts)})
}

func (s *Server) replayDelivery(w http.ResponseWriter, r *http.Request) {
	d, err := s.store.RequeueDelivery(r.Context(), owner(r), chi.URLParam(r, "id"), s.opts.MaxAttempts)
	if err != nil {
		s.storeErr(w, err)
		return
	}
	writeJSON(w, http.StatusAccepted, d)
}
