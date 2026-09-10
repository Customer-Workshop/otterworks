package httpapi

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/store"
	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/targets"
	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/rs/zerolog"
)

var allowedEvents = map[string]bool{"file.shared": true, "document.updated": true, "comment.added": true, "webhook.ping": true}

type API struct {
	store               store.Store
	logger              zerolog.Logger
	maxAttempts         int
	allowPrivateTargets bool
}

type Options struct {
	MaxAttempts         int
	AllowPrivateTargets bool
}

func NewRouter(s store.Store, logger zerolog.Logger, options ...Options) chi.Router {
	attempts := 5
	allowPrivateTargets := false
	if len(options) > 0 {
		if options[0].MaxAttempts > 0 {
			attempts = options[0].MaxAttempts
		}
		allowPrivateTargets = options[0].AllowPrivateTargets
	}
	api := &API{store: s, logger: logger, maxAttempts: attempts, allowPrivateTargets: allowPrivateTargets}
	r := chi.NewRouter()
	r.Use(headless)
	r.Use(requestLogger(logger))
	r.NotFound(func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "not found"})
	})
	r.MethodNotAllowed(func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
	})
	r.Get("/health", api.health)
	r.Route("/api/v1/webhooks", func(r chi.Router) {
		r.Use(identity)
		r.Post("/subscriptions", api.createSubscription)
		r.Get("/subscriptions", api.listSubscriptions)
		r.Get("/subscriptions/{id}", api.getSubscription)
		r.Delete("/subscriptions/{id}", api.deleteSubscription)
		r.Post("/subscriptions/{id}/test", api.testSubscription)
		r.Get("/deliveries", api.listDeliveries)
	})
	return r
}

func headless(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.Header.Get("X-Request-ID") == "" {
			r.Header.Set("X-Request-ID", uuid.NewString())
		}
		accept := strings.ToLower(r.Header.Get("Accept"))
		if strings.Contains(accept, "text/html") && !strings.Contains(accept, "application/json") && !strings.Contains(accept, "*/*") {
			writeJSON(w, http.StatusNotAcceptable, map[string]any{"error": "not acceptable", "accepts": []string{"application/json"}})
			return
		}
		next.ServeHTTP(&safeWriter{ResponseWriter: w}, r)
	})
}

type safeWriter struct{ http.ResponseWriter }

func (w *safeWriter) WriteHeader(status int) {
	w.Header().Del("Set-Cookie")
	w.Header().Set("Content-Type", "application/json")
	w.ResponseWriter.WriteHeader(status)
}
func (w *safeWriter) Write(data []byte) (int, error) {
	w.Header().Del("Set-Cookie")
	if w.Header().Get("Content-Type") == "" {
		w.Header().Set("Content-Type", "application/json")
	}
	return w.ResponseWriter.Write(data)
}
func (w *safeWriter) Header() http.Header { return w.ResponseWriter.Header() }

func requestLogger(logger zerolog.Logger) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			started := time.Now()
			next.ServeHTTP(w, r)
			logger.Info().Str("request_id", r.Header.Get("X-Request-ID")).Str("method", r.Method).Str("path", r.URL.Path).Dur("duration", time.Since(started)).Msg("request")
		})
	}
}
func identity(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.TrimSpace(r.Header.Get("X-User-ID")) == "" {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "unauthorized"})
			return
		}
		next.ServeHTTP(w, r)
	})
}
func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if status != http.StatusNoContent {
		_ = json.NewEncoder(w).Encode(value)
	}
}
func (a *API) health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "healthy", "version": "0.1.0"})
}
func newSecret() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return "whsec_" + hex.EncodeToString(b), nil
}

type subscriptionRequest struct {
	TargetURL   string   `json:"target_url"`
	EventTypes  []string `json:"event_types"`
	Description string   `json:"description"`
}

func validateSubscription(req subscriptionRequest, allowPrivate bool) error {
	if err := targets.Validate(req.TargetURL, allowPrivate); err != nil {
		return err
	}
	if len(req.EventTypes) == 0 {
		return fmt.Errorf("event_types must not be empty")
	}
	for _, event := range req.EventTypes {
		if !allowedEvents[event] {
			return fmt.Errorf("unsupported event type: %s", event)
		}
	}
	return nil
}
func (a *API) createSubscription(w http.ResponseWriter, r *http.Request) {
	var req subscriptionRequest
	if json.NewDecoder(r.Body).Decode(&req) != nil {
		writeJSON(w, 400, map[string]string{"error": "invalid JSON"})
		return
	}
	if err := validateSubscription(req, a.allowPrivateTargets); err != nil {
		writeJSON(w, 400, map[string]string{"error": err.Error()})
		return
	}
	secret, err := newSecret()
	if err != nil {
		writeJSON(w, 500, map[string]string{"error": "could not generate secret"})
		return
	}
	now := time.Now().UTC()
	sub := &store.Subscription{ID: uuid.New(), OwnerID: r.Header.Get("X-User-ID"), TargetURL: req.TargetURL, EventTypes: req.EventTypes, Description: req.Description, Secret: secret, Active: true, CreatedAt: now, UpdatedAt: now}
	if err := a.store.CreateSubscription(r.Context(), sub); err != nil {
		writeJSON(w, 500, map[string]string{"error": "could not create subscription"})
		return
	}
	writeJSON(w, 201, map[string]any{"id": sub.ID, "target_url": sub.TargetURL, "event_types": sub.EventTypes, "description": sub.Description, "active": sub.Active, "created_at": sub.CreatedAt, "secret": secret})
}
func publicSubscription(sub store.Subscription) map[string]any {
	return map[string]any{"id": sub.ID, "target_url": sub.TargetURL, "event_types": sub.EventTypes, "description": sub.Description, "active": sub.Active, "created_at": sub.CreatedAt}
}
func (a *API) listSubscriptions(w http.ResponseWriter, r *http.Request) {
	items, err := a.store.ListSubscriptions(r.Context(), r.Header.Get("X-User-ID"))
	if err != nil {
		writeJSON(w, 500, map[string]string{"error": "could not list subscriptions"})
		return
	}
	out := make([]any, 0, len(items))
	for _, item := range items {
		out = append(out, publicSubscription(item))
	}
	writeJSON(w, 200, map[string]any{"data": out})
}
func parseID(r *http.Request) (uuid.UUID, error) { return uuid.Parse(chi.URLParam(r, "id")) }
func (a *API) getSubscription(w http.ResponseWriter, r *http.Request) {
	id, err := parseID(r)
	if err != nil {
		writeJSON(w, 400, map[string]string{"error": "invalid subscription id"})
		return
	}
	sub, err := a.store.GetSubscription(r.Context(), r.Header.Get("X-User-ID"), id)
	if err == store.ErrNotFound {
		writeJSON(w, 404, map[string]string{"error": "not found"})
		return
	}
	if err != nil {
		writeJSON(w, 500, map[string]string{"error": "could not get subscription"})
		return
	}
	writeJSON(w, 200, publicSubscription(*sub))
}
func (a *API) deleteSubscription(w http.ResponseWriter, r *http.Request) {
	id, err := parseID(r)
	if err != nil {
		writeJSON(w, 400, map[string]string{"error": "invalid subscription id"})
		return
	}
	err = a.store.DeleteSubscription(r.Context(), r.Header.Get("X-User-ID"), id)
	if err == store.ErrNotFound {
		writeJSON(w, 404, map[string]string{"error": "not found"})
		return
	}
	if err != nil {
		writeJSON(w, 500, map[string]string{"error": "could not delete subscription"})
		return
	}
	writeJSON(w, 204, nil)
}
func (a *API) testSubscription(w http.ResponseWriter, r *http.Request) {
	id, err := parseID(r)
	if err != nil {
		writeJSON(w, 400, map[string]string{"error": "invalid subscription id"})
		return
	}
	sub, err := a.store.GetSubscription(r.Context(), r.Header.Get("X-User-ID"), id)
	if err == store.ErrNotFound {
		writeJSON(w, 404, map[string]string{"error": "not found"})
		return
	}
	if err != nil {
		writeJSON(w, 500, map[string]string{"error": "could not get subscription"})
		return
	}
	payload, _ := json.Marshal(map[string]any{"message": "ping", "subscription_id": id})
	now := time.Now().UTC()
	d := &store.Delivery{ID: uuid.New(), SubscriptionID: id, EventType: "webhook.ping", Payload: payload, Status: "pending", MaxAttempts: a.maxAttempts, NextAttemptAt: now, CreatedAt: now, UpdatedAt: now, TargetURL: sub.TargetURL, Secret: sub.Secret}
	if err := a.store.EnqueueDelivery(r.Context(), d); err != nil {
		writeJSON(w, 500, map[string]string{"error": "could not enqueue delivery"})
		return
	}
	writeJSON(w, 202, map[string]any{"delivery_id": d.ID, "status": "pending"})
}
func (a *API) listDeliveries(w http.ResponseWriter, r *http.Request) {
	var subID *uuid.UUID
	if raw := r.URL.Query().Get("subscription_id"); raw != "" {
		id, err := uuid.Parse(raw)
		if err != nil {
			writeJSON(w, 400, map[string]string{"error": "invalid subscription_id"})
			return
		}
		subID = &id
	}
	limit := 50
	if raw := r.URL.Query().Get("limit"); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed < 1 {
			writeJSON(w, 400, map[string]string{"error": "invalid limit"})
			return
		}
		if parsed > 100 {
			parsed = 100
		}
		limit = parsed
	}
	items, err := a.store.ListDeliveries(r.Context(), r.Header.Get("X-User-ID"), subID, limit)
	if err != nil {
		writeJSON(w, 500, map[string]string{"error": "could not list deliveries"})
		return
	}
	writeJSON(w, 200, map[string]any{"data": items})
}
