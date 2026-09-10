package store

import (
	"context"
	"errors"
	"sync"
	"time"

	"github.com/google/uuid"
)

var ErrNotFound = errors.New("not found")

type Subscription struct {
	ID          uuid.UUID `json:"id"`
	OwnerID     string    `json:"-"`
	TargetURL   string    `json:"target_url"`
	EventTypes  []string  `json:"event_types"`
	Description string    `json:"description,omitempty"`
	Secret      string    `json:"-"`
	Active      bool      `json:"active"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

type DeliveryAttempt struct {
	ID           uuid.UUID `json:"-"`
	DeliveryID   uuid.UUID `json:"-"`
	Attempt      int       `json:"attempt"`
	ResponseCode *int      `json:"response_code"`
	Error        *string   `json:"error"`
	DurationMS   int       `json:"duration_ms"`
	AttemptedAt  time.Time `json:"attempted_at"`
}

type Delivery struct {
	ID               uuid.UUID         `json:"id"`
	SubscriptionID   uuid.UUID         `json:"subscription_id"`
	EventType        string            `json:"event_type"`
	Payload          []byte            `json:"-"`
	Status           string            `json:"status"`
	Attempts         int               `json:"attempts"`
	MaxAttempts      int               `json:"max_attempts"`
	LastResponseCode *int              `json:"last_response_code"`
	LastError        *string           `json:"last_error"`
	NextAttemptAt    time.Time         `json:"next_attempt_at"`
	CreatedAt        time.Time         `json:"created_at"`
	UpdatedAt        time.Time         `json:"updated_at"`
	DeliveredAt      *time.Time        `json:"delivered_at"`
	AttemptsLog      []DeliveryAttempt `json:"attempts_log"`
	TargetURL        string            `json:"-"`
	Secret           string            `json:"-"`
}

type Store interface {
	CreateSubscription(context.Context, *Subscription) error
	ListSubscriptions(context.Context, string) ([]Subscription, error)
	GetSubscription(context.Context, string, uuid.UUID) (*Subscription, error)
	DeleteSubscription(context.Context, string, uuid.UUID) error
	ListActiveSubscriptionsForEvent(context.Context, string) ([]Subscription, error)
	EnqueueDelivery(context.Context, *Delivery) error
	ListDeliveries(context.Context, string, *uuid.UUID, int) ([]Delivery, error)
	ClaimDueDeliveries(context.Context, int) ([]Delivery, error)
	RecordAttempt(context.Context, *DeliveryAttempt) error
	MarkDelivered(context.Context, uuid.UUID, time.Time) error
	MarkRetry(context.Context, uuid.UUID, time.Time) error
	MarkFailed(context.Context, uuid.UUID) error
	Close()
}

type MemoryStore struct {
	mu            sync.Mutex
	subscriptions map[uuid.UUID]Subscription
	deliveries    map[uuid.UUID]Delivery
	attempts      map[uuid.UUID][]DeliveryAttempt
}

func NewMemoryStore() *MemoryStore {
	return &MemoryStore{subscriptions: make(map[uuid.UUID]Subscription), deliveries: make(map[uuid.UUID]Delivery), attempts: make(map[uuid.UUID][]DeliveryAttempt)}
}
func (s *MemoryStore) CreateSubscription(_ context.Context, sub *Subscription) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.subscriptions[sub.ID] = *sub
	return nil
}
func (s *MemoryStore) ListSubscriptions(_ context.Context, owner string) ([]Subscription, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	var out []Subscription
	for _, sub := range s.subscriptions {
		if sub.OwnerID == owner {
			out = append(out, sub)
		}
	}
	return out, nil
}
func (s *MemoryStore) GetSubscription(_ context.Context, owner string, id uuid.UUID) (*Subscription, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	sub, ok := s.subscriptions[id]
	if !ok || sub.OwnerID != owner {
		return nil, ErrNotFound
	}
	copy := sub
	return &copy, nil
}
func (s *MemoryStore) DeleteSubscription(_ context.Context, owner string, id uuid.UUID) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	sub, ok := s.subscriptions[id]
	if !ok || sub.OwnerID != owner {
		return ErrNotFound
	}
	delete(s.subscriptions, id)
	for id, d := range s.deliveries {
		if d.SubscriptionID == sub.ID {
			delete(s.deliveries, id)
		}
	}
	return nil
}
func (s *MemoryStore) ListActiveSubscriptionsForEvent(_ context.Context, event string) ([]Subscription, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	var out []Subscription
	for _, sub := range s.subscriptions {
		if sub.Active && contains(sub.EventTypes, event) {
			out = append(out, sub)
		}
	}
	return out, nil
}
func (s *MemoryStore) EnqueueDelivery(_ context.Context, d *Delivery) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if d.ID == uuid.Nil {
		d.ID = uuid.New()
	}
	if d.CreatedAt.IsZero() {
		d.CreatedAt = time.Now().UTC()
	}
	d.UpdatedAt = d.CreatedAt
	if d.Status == "" {
		d.Status = "pending"
	}
	if d.MaxAttempts == 0 {
		d.MaxAttempts = 5
	}
	if d.NextAttemptAt.IsZero() {
		d.NextAttemptAt = d.CreatedAt
	}
	if sub, ok := s.subscriptions[d.SubscriptionID]; ok {
		d.TargetURL, d.Secret = sub.TargetURL, sub.Secret
	}
	s.deliveries[d.ID] = *d
	return nil
}
func (s *MemoryStore) ListDeliveries(_ context.Context, owner string, subID *uuid.UUID, limit int) ([]Delivery, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	var out []Delivery
	for _, d := range s.deliveries {
		sub, ok := s.subscriptions[d.SubscriptionID]
		if !ok || sub.OwnerID != owner || subID != nil && d.SubscriptionID != *subID {
			continue
		}
		d.AttemptsLog = append([]DeliveryAttempt(nil), s.attempts[d.ID]...)
		out = append(out, d)
		if len(out) >= limit {
			break
		}
	}
	return out, nil
}
func (s *MemoryStore) ClaimDueDeliveries(_ context.Context, limit int) ([]Delivery, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	now := time.Now()
	var out []Delivery
	for id, d := range s.deliveries {
		if d.Status == "pending" && !d.NextAttemptAt.After(now) {
			d.Status = "pending"
			s.deliveries[id] = d
			out = append(out, d)
			if len(out) >= limit {
				break
			}
		}
	}
	return out, nil
}
func (s *MemoryStore) RecordAttempt(_ context.Context, a *DeliveryAttempt) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	d, ok := s.deliveries[a.DeliveryID]
	if !ok {
		return ErrNotFound
	}
	d.Attempts = a.Attempt
	d.LastResponseCode, d.LastError = a.ResponseCode, a.Error
	d.UpdatedAt = time.Now().UTC()
	s.deliveries[d.ID] = d
	s.attempts[d.ID] = append(s.attempts[d.ID], *a)
	return nil
}
func (s *MemoryStore) MarkDelivered(_ context.Context, id uuid.UUID, at time.Time) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	d, ok := s.deliveries[id]
	if !ok {
		return ErrNotFound
	}
	d.Status, d.DeliveredAt, d.UpdatedAt = "delivered", &at, at
	s.deliveries[id] = d
	return nil
}
func (s *MemoryStore) MarkRetry(_ context.Context, id uuid.UUID, at time.Time) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	d, ok := s.deliveries[id]
	if !ok {
		return ErrNotFound
	}
	d.Status, d.NextAttemptAt, d.UpdatedAt = "pending", at, time.Now().UTC()
	s.deliveries[id] = d
	return nil
}
func (s *MemoryStore) MarkFailed(_ context.Context, id uuid.UUID) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	d, ok := s.deliveries[id]
	if !ok {
		return ErrNotFound
	}
	d.Status, d.UpdatedAt = "failed", time.Now().UTC()
	s.deliveries[id] = d
	return nil
}
func (s *MemoryStore) Close() {}
func contains(values []string, want string) bool {
	for _, value := range values {
		if value == want {
			return true
		}
	}
	return false
}
