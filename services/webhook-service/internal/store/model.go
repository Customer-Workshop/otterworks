package store

import (
	"context"
	"encoding/json"
	"errors"
	"time"
)

// ErrNotFound is returned when a subscription or delivery does not exist.
var ErrNotFound = errors.New("not found")

// Delivery lifecycle states.
const (
	StatusPending    = "pending"
	StatusRetrying   = "retrying"
	StatusDelivered  = "delivered"
	StatusDeadLetter = "dead_letter"
)

// Subscription is an outbound webhook registration owned by one user.
type Subscription struct {
	ID          string    `json:"id"`
	OwnerID     string    `json:"ownerId"`
	URL         string    `json:"url"`
	Description string    `json:"description"`
	EventTypes  []string  `json:"eventTypes"`
	Secret      string    `json:"-"`
	Active      bool      `json:"active"`
	CreatedAt   time.Time `json:"createdAt"`
	UpdatedAt   time.Time `json:"updatedAt"`
}

// Delivery is a single event fan-out to one subscription. It carries the
// signed payload and is retried until delivered or dead-lettered.
type Delivery struct {
	ID             string          `json:"id"`
	SubscriptionID string          `json:"subscriptionId"`
	OwnerID        string          `json:"ownerId"`
	EventID        string          `json:"eventId"`
	EventType      string          `json:"eventType"`
	Payload        json.RawMessage `json:"payload"`
	Status         string          `json:"status"`
	Attempts       int             `json:"attempts"`
	MaxAttempts    int             `json:"maxAttempts"`
	NextAttemptAt  *time.Time      `json:"nextAttemptAt,omitempty"`
	LastError      string          `json:"lastError,omitempty"`
	LastStatusCode int             `json:"lastStatusCode,omitempty"`
	DeliveredAt    *time.Time      `json:"deliveredAt,omitempty"`
	DeadLetteredAt *time.Time      `json:"deadLetteredAt,omitempty"`
	CreatedAt      time.Time       `json:"createdAt"`
	UpdatedAt      time.Time       `json:"updatedAt"`
}

// Attempt is one HTTP attempt of a delivery, kept for the queryable log.
type Attempt struct {
	ID           string    `json:"id"`
	DeliveryID   string    `json:"deliveryId"`
	Number       int       `json:"number"`
	StatusCode   int       `json:"statusCode,omitempty"`
	Error        string    `json:"error,omitempty"`
	ResponseBody string    `json:"responseBody,omitempty"`
	DurationMs   int64     `json:"durationMs"`
	AttemptedAt  time.Time `json:"attemptedAt"`
}

// DeliveryFilter narrows delivery-log queries.
type DeliveryFilter struct {
	OwnerID        string
	SubscriptionID string
	EventType      string
	Status         string
	Since          *time.Time
	Limit          int
	Cursor         string
}

// AttemptResult is what the dispatcher records after one HTTP attempt.
type AttemptResult struct {
	StatusCode   int
	Error        string
	ResponseBody string
	Duration     time.Duration
	AttemptedAt  time.Time
	// Outcome
	Success       bool
	NextAttemptAt *time.Time // nil when Success or DeadLetter
	DeadLetter    bool
}

// Store is the persistence contract shared by the API and the dispatcher.
type Store interface {
	Migrate(ctx context.Context) error
	Ping(ctx context.Context) error

	CreateSubscription(ctx context.Context, s *Subscription) error
	GetSubscription(ctx context.Context, ownerID, id string) (*Subscription, error)
	ListSubscriptions(ctx context.Context, ownerID string) ([]*Subscription, error)
	UpdateSubscription(ctx context.Context, s *Subscription) error
	DeleteSubscription(ctx context.Context, ownerID, id string) error
	ActiveSubscriptionsForEvent(ctx context.Context, eventType string) ([]*Subscription, error)

	CreateDeliveries(ctx context.Context, ds []*Delivery) error
	GetDelivery(ctx context.Context, ownerID, id string) (*Delivery, error)
	ListDeliveries(ctx context.Context, f DeliveryFilter) ([]*Delivery, string, error)
	ListAttempts(ctx context.Context, deliveryID string) ([]*Attempt, error)
	// ClaimDueDeliveries atomically leases up to limit deliveries whose next
	// attempt is due, so concurrent workers never double-send.
	ClaimDueDeliveries(ctx context.Context, now time.Time, limit int) ([]*Delivery, error)
	RecordAttempt(ctx context.Context, d *Delivery, r AttemptResult) error
	// RequeueDelivery resets a dead-lettered (or any) delivery for immediate retry.
	RequeueDelivery(ctx context.Context, ownerID, id string, maxAttempts int) (*Delivery, error)
	// SubscriptionSecret returns the signing secret even when the caller has no owner context.
	SubscriptionSecret(ctx context.Context, id string) (string, error)
	Stats(ctx context.Context, ownerID string) (map[string]int, error)
}
