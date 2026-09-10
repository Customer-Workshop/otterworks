package store

import (
	"context"
	"encoding/json"
	"errors"
	"time"
)

// ErrNotFound is returned when a subscription or delivery does not exist.
var ErrNotFound = errors.New("not found")

// ErrInvalidCursor is returned when a pagination cursor cannot be decoded.
var ErrInvalidCursor = errors.New("invalid cursor")

// ErrConflict is returned when a delivery is not in a state that permits the
// requested transition (e.g. replaying a delivery that is still in flight).
var ErrConflict = errors.New("conflicting delivery state")

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
	// UpdateSubscription writes every mutable column except the secret, so a
	// stale read can never undo a concurrent RotateSecret.
	UpdateSubscription(ctx context.Context, s *Subscription) error
	RotateSecret(ctx context.Context, ownerID, id, secret string, now time.Time) error
	DeleteSubscription(ctx context.Context, ownerID, id string) error
	// ActiveSubscriptionsForEvent returns ownerID's active subscriptions that
	// match eventType (exactly or via "*"). Events never fan out across owners.
	ActiveSubscriptionsForEvent(ctx context.Context, ownerID, eventType string) ([]*Subscription, error)

	CreateDeliveries(ctx context.Context, ds []*Delivery) error
	GetDelivery(ctx context.Context, ownerID, id string) (*Delivery, error)
	ListDeliveries(ctx context.Context, f DeliveryFilter) ([]*Delivery, string, error)
	ListAttempts(ctx context.Context, deliveryID string) ([]*Attempt, error)
	// ClaimDueDeliveries atomically leases up to limit deliveries whose next
	// attempt is due, so concurrent workers never double-send.
	ClaimDueDeliveries(ctx context.Context, now time.Time, lease time.Duration, limit int) ([]*Delivery, error)
	RecordAttempt(ctx context.Context, d *Delivery, r AttemptResult) error
	// RequeueDelivery resets a dead-lettered delivery for immediate retry. The
	// status predicate is enforced atomically in the store so a replay can never
	// race a dispatcher that still holds the lease; non-terminal deliveries
	// return ErrConflict.
	RequeueDelivery(ctx context.Context, ownerID, id string, maxAttempts int) (*Delivery, error)
	// SubscriptionSecret returns the signing secret even when the caller has no owner context.
	SubscriptionSecret(ctx context.Context, id string) (string, error)
	Stats(ctx context.Context, ownerID string) (map[string]int, error)
}
