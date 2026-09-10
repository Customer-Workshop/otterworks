package store

import (
	"context"
	"sort"
	"sync"
	"time"

	"github.com/google/uuid"
)

// Memory is an in-process Store used by tests and the headless smoke suite.
type Memory struct {
	mu       sync.Mutex
	subs     map[string]*Subscription
	dels     map[string]*Delivery
	attempts map[string][]*Attempt
	leases   map[string]time.Time
}

// NewMemory returns an empty in-memory store.
func NewMemory() *Memory {
	return &Memory{
		subs:     map[string]*Subscription{},
		dels:     map[string]*Delivery{},
		attempts: map[string][]*Attempt{},
		leases:   map[string]time.Time{},
	}
}

func (m *Memory) Migrate(context.Context) error { return nil }
func (m *Memory) Ping(context.Context) error    { return nil }

func cloneSub(s *Subscription) *Subscription {
	c := *s
	c.EventTypes = append([]string(nil), s.EventTypes...)
	return &c
}

func cloneDel(d *Delivery) *Delivery {
	c := *d
	c.Payload = append([]byte(nil), d.Payload...)
	return &c
}

func (m *Memory) CreateSubscription(_ context.Context, s *Subscription) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.subs[s.ID] = cloneSub(s)
	return nil
}

func (m *Memory) GetSubscription(_ context.Context, ownerID, id string) (*Subscription, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	s, ok := m.subs[id]
	if !ok || s.OwnerID != ownerID {
		return nil, ErrNotFound
	}
	return cloneSub(s), nil
}

func (m *Memory) ListSubscriptions(_ context.Context, ownerID string) ([]*Subscription, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := []*Subscription{}
	for _, s := range m.subs {
		if s.OwnerID == ownerID {
			out = append(out, cloneSub(s))
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].CreatedAt.After(out[j].CreatedAt) })
	return out, nil
}

func (m *Memory) UpdateSubscription(_ context.Context, s *Subscription) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	cur, ok := m.subs[s.ID]
	if !ok || cur.OwnerID != s.OwnerID {
		return ErrNotFound
	}
	next := cloneSub(s)
	next.Secret = cur.Secret
	m.subs[s.ID] = next
	return nil
}

func (m *Memory) RotateSecret(_ context.Context, ownerID, id, secret string, now time.Time) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	cur, ok := m.subs[id]
	if !ok || cur.OwnerID != ownerID {
		return ErrNotFound
	}
	cur.Secret = secret
	cur.UpdatedAt = now
	return nil
}

func (m *Memory) DeleteSubscription(_ context.Context, ownerID, id string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	cur, ok := m.subs[id]
	if !ok || cur.OwnerID != ownerID {
		return ErrNotFound
	}
	delete(m.subs, id)
	for did, d := range m.dels {
		if d.SubscriptionID == id {
			delete(m.dels, did)
			delete(m.attempts, did)
		}
	}
	return nil
}

func (m *Memory) ActiveSubscriptionsForEvent(_ context.Context, ownerID, eventType string) ([]*Subscription, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := []*Subscription{}
	for _, s := range m.subs {
		if !s.Active || s.OwnerID != ownerID {
			continue
		}
		for _, et := range s.EventTypes {
			if et == eventType || et == "*" {
				out = append(out, cloneSub(s))
				break
			}
		}
	}
	return out, nil
}

func (m *Memory) SubscriptionSecret(_ context.Context, id string) (string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	s, ok := m.subs[id]
	if !ok {
		return "", ErrNotFound
	}
	return s.Secret, nil
}

func (m *Memory) CreateDeliveries(_ context.Context, ds []*Delivery) error {
	m.mu.Lock()
	defer m.mu.Unlock()
outer:
	for _, d := range ds {
		for _, existing := range m.dels {
			if existing.SubscriptionID == d.SubscriptionID && existing.EventID == d.EventID {
				continue outer
			}
		}
		m.dels[d.ID] = cloneDel(d)
	}
	return nil
}

func (m *Memory) GetDelivery(_ context.Context, ownerID, id string) (*Delivery, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	d, ok := m.dels[id]
	if !ok || d.OwnerID != ownerID {
		return nil, ErrNotFound
	}
	return cloneDel(d), nil
}

func (m *Memory) ListDeliveries(_ context.Context, f DeliveryFilter) ([]*Delivery, string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	limit := f.Limit
	if limit <= 0 || limit > 200 {
		limit = 50
	}
	var cursorT time.Time
	var cursorID string
	if f.Cursor != "" {
		var err error
		if cursorT, cursorID, err = decodeCursor(f.Cursor); err != nil {
			return nil, "", err
		}
	}
	out := []*Delivery{}
	for _, d := range m.dels {
		if d.OwnerID != f.OwnerID ||
			(f.SubscriptionID != "" && d.SubscriptionID != f.SubscriptionID) ||
			(f.EventType != "" && d.EventType != f.EventType) ||
			(f.Status != "" && d.Status != f.Status) ||
			(f.Since != nil && d.CreatedAt.Before(*f.Since)) {
			continue
		}
		if f.Cursor != "" && !(d.CreatedAt.Before(cursorT) || (d.CreatedAt.Equal(cursorT) && d.ID < cursorID)) {
			continue
		}
		out = append(out, cloneDel(d))
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].CreatedAt.Equal(out[j].CreatedAt) {
			return out[i].ID > out[j].ID
		}
		return out[i].CreatedAt.After(out[j].CreatedAt)
	})
	next := ""
	if len(out) > limit {
		out = out[:limit]
		last := out[len(out)-1]
		next = encodeCursor(last.CreatedAt, last.ID)
	}
	return out, next, nil
}

func (m *Memory) ListAttempts(_ context.Context, deliveryID string) ([]*Attempt, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := make([]*Attempt, 0, len(m.attempts[deliveryID]))
	for _, a := range m.attempts[deliveryID] {
		c := *a
		out = append(out, &c)
	}
	return out, nil
}

func (m *Memory) ClaimDueDeliveries(_ context.Context, now time.Time, lease time.Duration, limit int) ([]*Delivery, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := []*Delivery{}
	for _, d := range m.dels {
		if len(out) >= limit {
			break
		}
		if (d.Status == StatusPending || d.Status == StatusRetrying) && d.NextAttemptAt != nil && !d.NextAttemptAt.After(now) {
			if until, ok := m.leases[d.ID]; ok && until.After(now) {
				continue
			}
			m.leases[d.ID] = now.Add(lease)
			out = append(out, cloneDel(d))
		}
	}
	return out, nil
}

func (m *Memory) RecordAttempt(_ context.Context, d *Delivery, r AttemptResult) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	cur, ok := m.dels[d.ID]
	if !ok {
		return ErrNotFound
	}
	number := cur.Attempts + 1
	m.attempts[d.ID] = append(m.attempts[d.ID], &Attempt{
		ID: uuid.NewString(), DeliveryID: d.ID, Number: number, StatusCode: r.StatusCode,
		Error: r.Error, ResponseBody: r.ResponseBody, DurationMs: r.Duration.Milliseconds(), AttemptedAt: r.AttemptedAt,
	})
	cur.Attempts = number
	cur.LastError, cur.LastStatusCode, cur.NextAttemptAt, cur.UpdatedAt = r.Error, r.StatusCode, r.NextAttemptAt, r.AttemptedAt
	at := r.AttemptedAt
	switch {
	case r.Success:
		cur.Status, cur.DeliveredAt = StatusDelivered, &at
	case r.DeadLetter:
		cur.Status, cur.DeadLetteredAt = StatusDeadLetter, &at
	default:
		cur.Status = StatusRetrying
	}
	delete(m.leases, d.ID)
	*d = *cloneDel(cur)
	return nil
}

func (m *Memory) RequeueDelivery(_ context.Context, ownerID, id string, maxAttempts int) (*Delivery, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	d, ok := m.dels[id]
	if !ok || d.OwnerID != ownerID {
		return nil, ErrNotFound
	}
	if d.Status != StatusDeadLetter {
		return nil, ErrConflict
	}
	now := time.Now().UTC()
	d.Status, d.NextAttemptAt, d.DeadLetteredAt, d.UpdatedAt = StatusPending, &now, nil, now
	d.MaxAttempts = d.Attempts + maxAttempts
	delete(m.leases, id)
	return cloneDel(d), nil
}

func (m *Memory) Stats(_ context.Context, ownerID string) (map[string]int, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := map[string]int{StatusPending: 0, StatusRetrying: 0, StatusDelivered: 0, StatusDeadLetter: 0}
	for _, d := range m.dels {
		if d.OwnerID == ownerID {
			out[d.Status]++
		}
	}
	return out, nil
}
