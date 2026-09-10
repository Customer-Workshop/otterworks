package store

import (
	"context"
	"encoding/base64"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

const schema = `
CREATE TABLE IF NOT EXISTS webhook_subscriptions (
    id           UUID PRIMARY KEY,
    owner_id     TEXT NOT NULL,
    url          TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    event_types  TEXT[] NOT NULL,
    secret       TEXT NOT NULL,
    active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS webhook_subscriptions_owner_idx ON webhook_subscriptions (owner_id);
CREATE INDEX IF NOT EXISTS webhook_subscriptions_events_idx ON webhook_subscriptions USING GIN (event_types);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id               UUID PRIMARY KEY,
    subscription_id  UUID NOT NULL REFERENCES webhook_subscriptions(id) ON DELETE CASCADE,
    owner_id         TEXT NOT NULL,
    event_id         TEXT NOT NULL,
    event_type       TEXT NOT NULL,
    payload          JSONB NOT NULL,
    status           TEXT NOT NULL,
    attempts         INT NOT NULL DEFAULT 0,
    max_attempts     INT NOT NULL,
    next_attempt_at  TIMESTAMPTZ,
    locked_until     TIMESTAMPTZ,
    last_error       TEXT NOT NULL DEFAULT '',
    last_status_code INT NOT NULL DEFAULT 0,
    delivered_at     TIMESTAMPTZ,
    dead_lettered_at TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (subscription_id, event_id)
);
CREATE INDEX IF NOT EXISTS webhook_deliveries_due_idx ON webhook_deliveries (next_attempt_at) WHERE status IN ('pending','retrying');
CREATE INDEX IF NOT EXISTS webhook_deliveries_owner_created_idx ON webhook_deliveries (owner_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS webhook_deliveries_sub_idx ON webhook_deliveries (subscription_id);

CREATE TABLE IF NOT EXISTS webhook_delivery_attempts (
    id            UUID PRIMARY KEY,
    delivery_id   UUID NOT NULL REFERENCES webhook_deliveries(id) ON DELETE CASCADE,
    number        INT NOT NULL,
    status_code   INT NOT NULL DEFAULT 0,
    error         TEXT NOT NULL DEFAULT '',
    response_body TEXT NOT NULL DEFAULT '',
    duration_ms   BIGINT NOT NULL DEFAULT 0,
    attempted_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS webhook_delivery_attempts_delivery_idx ON webhook_delivery_attempts (delivery_id, number);
`

// Postgres implements Store on top of pgx.
type Postgres struct {
	pool *pgxpool.Pool
}

// NewPostgres connects to the database.
func NewPostgres(ctx context.Context, url string) (*Postgres, error) {
	pool, err := pgxpool.New(ctx, url)
	if err != nil {
		return nil, fmt.Errorf("connect postgres: %w", err)
	}
	return &Postgres{pool: pool}, nil
}

// Close releases the pool.
func (p *Postgres) Close() { p.pool.Close() }

func (p *Postgres) Migrate(ctx context.Context) error {
	_, err := p.pool.Exec(ctx, schema)
	return err
}

func (p *Postgres) Ping(ctx context.Context) error { return p.pool.Ping(ctx) }

const subCols = `id, owner_id, url, description, event_types, secret, active, created_at, updated_at`

func scanSub(row pgx.Row) (*Subscription, error) {
	s := &Subscription{}
	err := row.Scan(&s.ID, &s.OwnerID, &s.URL, &s.Description, &s.EventTypes, &s.Secret, &s.Active, &s.CreatedAt, &s.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	return s, err
}

func (p *Postgres) CreateSubscription(ctx context.Context, s *Subscription) error {
	_, err := p.pool.Exec(ctx, `INSERT INTO webhook_subscriptions (`+subCols+`) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)`,
		s.ID, s.OwnerID, s.URL, s.Description, s.EventTypes, s.Secret, s.Active, s.CreatedAt, s.UpdatedAt)
	return err
}

func (p *Postgres) GetSubscription(ctx context.Context, ownerID, id string) (*Subscription, error) {
	return scanSub(p.pool.QueryRow(ctx, `SELECT `+subCols+` FROM webhook_subscriptions WHERE owner_id=$1 AND id=$2`, ownerID, id))
}

func (p *Postgres) ListSubscriptions(ctx context.Context, ownerID string) ([]*Subscription, error) {
	rows, err := p.pool.Query(ctx, `SELECT `+subCols+` FROM webhook_subscriptions WHERE owner_id=$1 ORDER BY created_at DESC`, ownerID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return collectSubs(rows)
}

func collectSubs(rows pgx.Rows) ([]*Subscription, error) {
	out := []*Subscription{}
	for rows.Next() {
		s, err := scanSub(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, s)
	}
	return out, rows.Err()
}

func (p *Postgres) UpdateSubscription(ctx context.Context, s *Subscription) error {
	tag, err := p.pool.Exec(ctx, `UPDATE webhook_subscriptions SET url=$3, description=$4, event_types=$5, active=$6, updated_at=$7 WHERE owner_id=$1 AND id=$2`,
		s.OwnerID, s.ID, s.URL, s.Description, s.EventTypes, s.Active, s.UpdatedAt)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (p *Postgres) RotateSecret(ctx context.Context, ownerID, id, secret string, now time.Time) error {
	tag, err := p.pool.Exec(ctx, `UPDATE webhook_subscriptions SET secret=$3, updated_at=$4 WHERE owner_id=$1 AND id=$2`,
		ownerID, id, secret, now)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (p *Postgres) DeleteSubscription(ctx context.Context, ownerID, id string) error {
	tag, err := p.pool.Exec(ctx, `DELETE FROM webhook_subscriptions WHERE owner_id=$1 AND id=$2`, ownerID, id)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (p *Postgres) ActiveSubscriptionsForEvent(ctx context.Context, ownerID, eventType string) ([]*Subscription, error) {
	rows, err := p.pool.Query(ctx, `SELECT `+subCols+` FROM webhook_subscriptions WHERE owner_id=$1 AND active AND (event_types @> ARRAY[$2]::text[] OR event_types @> ARRAY['*']::text[])`, ownerID, eventType)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return collectSubs(rows)
}

func (p *Postgres) SubscriptionSecret(ctx context.Context, id string) (string, error) {
	var secret string
	err := p.pool.QueryRow(ctx, `SELECT secret FROM webhook_subscriptions WHERE id=$1`, id).Scan(&secret)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", ErrNotFound
	}
	return secret, err
}

const delCols = `id, subscription_id, owner_id, event_id, event_type, payload, status, attempts, max_attempts, next_attempt_at, last_error, last_status_code, delivered_at, dead_lettered_at, created_at, updated_at`

func scanDel(row pgx.Row) (*Delivery, error) {
	d := &Delivery{}
	err := row.Scan(&d.ID, &d.SubscriptionID, &d.OwnerID, &d.EventID, &d.EventType, &d.Payload, &d.Status, &d.Attempts, &d.MaxAttempts,
		&d.NextAttemptAt, &d.LastError, &d.LastStatusCode, &d.DeliveredAt, &d.DeadLetteredAt, &d.CreatedAt, &d.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	return d, err
}

func (p *Postgres) CreateDeliveries(ctx context.Context, ds []*Delivery) error {
	if len(ds) == 0 {
		return nil
	}
	batch := &pgx.Batch{}
	for _, d := range ds {
		// ON CONFLICT makes SQS at-least-once redelivery idempotent per (subscription, event).
		batch.Queue(`INSERT INTO webhook_deliveries (`+delCols+`) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16) ON CONFLICT (subscription_id, event_id) DO NOTHING`,
			d.ID, d.SubscriptionID, d.OwnerID, d.EventID, d.EventType, d.Payload, d.Status, d.Attempts, d.MaxAttempts, d.NextAttemptAt,
			d.LastError, d.LastStatusCode, d.DeliveredAt, d.DeadLetteredAt, d.CreatedAt, d.UpdatedAt)
	}
	res := p.pool.SendBatch(ctx, batch)
	defer res.Close()
	for range ds {
		if _, err := res.Exec(); err != nil {
			return err
		}
	}
	return nil
}

func (p *Postgres) GetDelivery(ctx context.Context, ownerID, id string) (*Delivery, error) {
	return scanDel(p.pool.QueryRow(ctx, `SELECT `+delCols+` FROM webhook_deliveries WHERE owner_id=$1 AND id=$2`, ownerID, id))
}

func encodeCursor(t time.Time, id string) string {
	return base64.RawURLEncoding.EncodeToString([]byte(t.UTC().Format(time.RFC3339Nano) + "|" + id))
}

func decodeCursor(c string) (time.Time, string, error) {
	raw, err := base64.RawURLEncoding.DecodeString(c)
	if err != nil {
		return time.Time{}, "", ErrInvalidCursor
	}
	parts := strings.SplitN(string(raw), "|", 2)
	if len(parts) != 2 {
		return time.Time{}, "", ErrInvalidCursor
	}
	t, err := time.Parse(time.RFC3339Nano, parts[0])
	if err != nil {
		return time.Time{}, "", ErrInvalidCursor
	}
	if _, err := uuid.Parse(parts[1]); err != nil {
		return time.Time{}, "", ErrInvalidCursor
	}
	return t, parts[1], nil
}

func (p *Postgres) ListDeliveries(ctx context.Context, f DeliveryFilter) ([]*Delivery, string, error) {
	limit := f.Limit
	if limit <= 0 || limit > 200 {
		limit = 50
	}
	where := []string{"owner_id=$1"}
	args := []any{f.OwnerID}
	add := func(cond string, v any) {
		args = append(args, v)
		where = append(where, fmt.Sprintf(cond, len(args)))
	}
	if f.SubscriptionID != "" {
		add("subscription_id=$%d", f.SubscriptionID)
	}
	if f.EventType != "" {
		add("event_type=$%d", f.EventType)
	}
	if f.Status != "" {
		add("status=$%d", f.Status)
	}
	if f.Since != nil {
		add("created_at >= $%d", *f.Since)
	}
	if f.Cursor != "" {
		t, id, err := decodeCursor(f.Cursor)
		if err != nil {
			return nil, "", err
		}
		args = append(args, t, id)
		where = append(where, fmt.Sprintf("(created_at, id) < ($%d, $%d::uuid)", len(args)-1, len(args)))
	}
	args = append(args, limit+1)
	q := `SELECT ` + delCols + ` FROM webhook_deliveries WHERE ` + strings.Join(where, " AND ") +
		fmt.Sprintf(` ORDER BY created_at DESC, id DESC LIMIT $%d`, len(args))
	rows, err := p.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, "", err
	}
	defer rows.Close()
	out := []*Delivery{}
	for rows.Next() {
		d, err := scanDel(rows)
		if err != nil {
			return nil, "", err
		}
		out = append(out, d)
	}
	if err := rows.Err(); err != nil {
		return nil, "", err
	}
	next := ""
	if len(out) > limit {
		out = out[:limit]
		last := out[len(out)-1]
		next = encodeCursor(last.CreatedAt, last.ID)
	}
	return out, next, nil
}

func (p *Postgres) ListAttempts(ctx context.Context, deliveryID string) ([]*Attempt, error) {
	rows, err := p.pool.Query(ctx, `SELECT id, delivery_id, number, status_code, error, response_body, duration_ms, attempted_at FROM webhook_delivery_attempts WHERE delivery_id=$1 ORDER BY number`, deliveryID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []*Attempt{}
	for rows.Next() {
		a := &Attempt{}
		if err := rows.Scan(&a.ID, &a.DeliveryID, &a.Number, &a.StatusCode, &a.Error, &a.ResponseBody, &a.DurationMs, &a.AttemptedAt); err != nil {
			return nil, err
		}
		out = append(out, a)
	}
	return out, rows.Err()
}

func (p *Postgres) ClaimDueDeliveries(ctx context.Context, now time.Time, lease time.Duration, limit int) ([]*Delivery, error) {
	// Leased rows become visible again after the lease so a crashed worker's
	// claims are eventually retried.
	rows, err := p.pool.Query(ctx, `
		WITH due AS (
			SELECT id FROM webhook_deliveries
			WHERE status IN ('pending','retrying')
			  AND next_attempt_at <= $1
			  AND (locked_until IS NULL OR locked_until < $1)
			ORDER BY next_attempt_at
			LIMIT $2
			FOR UPDATE SKIP LOCKED
		)
		UPDATE webhook_deliveries d SET locked_until = $3
		FROM due WHERE d.id = due.id
		RETURNING `+prefixed("d.", delCols), now, limit, now.Add(lease))
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []*Delivery{}
	for rows.Next() {
		d, err := scanDel(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, d)
	}
	return out, rows.Err()
}

func prefixed(prefix, cols string) string {
	parts := strings.Split(cols, ", ")
	for i := range parts {
		parts[i] = prefix + parts[i]
	}
	return strings.Join(parts, ", ")
}

func (p *Postgres) RecordAttempt(ctx context.Context, d *Delivery, r AttemptResult) error {
	tx, err := p.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	number := d.Attempts + 1
	if _, err := tx.Exec(ctx, `INSERT INTO webhook_delivery_attempts (id, delivery_id, number, status_code, error, response_body, duration_ms, attempted_at) VALUES (gen_random_uuid(),$1,$2,$3,$4,$5,$6,$7)`,
		d.ID, number, r.StatusCode, r.Error, r.ResponseBody, r.Duration.Milliseconds(), r.AttemptedAt); err != nil {
		return err
	}

	status := StatusRetrying
	var deliveredAt, deadAt *time.Time
	switch {
	case r.Success:
		status = StatusDelivered
		deliveredAt = &r.AttemptedAt
	case r.DeadLetter:
		status = StatusDeadLetter
		deadAt = &r.AttemptedAt
	}
	if _, err := tx.Exec(ctx, `UPDATE webhook_deliveries SET attempts=$2, status=$3, next_attempt_at=$4, locked_until=NULL, last_error=$5, last_status_code=$6, delivered_at=COALESCE($7, delivered_at), dead_lettered_at=$8, updated_at=$9 WHERE id=$1`,
		d.ID, number, status, r.NextAttemptAt, r.Error, r.StatusCode, deliveredAt, deadAt, r.AttemptedAt); err != nil {
		return err
	}
	d.Attempts, d.Status, d.NextAttemptAt, d.LastError, d.LastStatusCode = number, status, r.NextAttemptAt, r.Error, r.StatusCode
	return tx.Commit(ctx)
}

func (p *Postgres) RequeueDelivery(ctx context.Context, ownerID, id string, maxAttempts int) (*Delivery, error) {
	now := time.Now().UTC()
	d, err := scanDel(p.pool.QueryRow(ctx, `UPDATE webhook_deliveries SET status='pending', next_attempt_at=$3, locked_until=NULL, dead_lettered_at=NULL, max_attempts=attempts+$4, updated_at=$3 WHERE owner_id=$1 AND id=$2 AND status=$5 RETURNING `+delCols,
		ownerID, id, now, maxAttempts, StatusDeadLetter))
	if errors.Is(err, ErrNotFound) {
		if _, getErr := p.GetDelivery(ctx, ownerID, id); getErr == nil {
			return nil, ErrConflict
		}
	}
	return d, err
}

func (p *Postgres) Stats(ctx context.Context, ownerID string) (map[string]int, error) {
	rows, err := p.pool.Query(ctx, `SELECT status, count(*) FROM webhook_deliveries WHERE owner_id=$1 GROUP BY status`, ownerID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := map[string]int{StatusPending: 0, StatusRetrying: 0, StatusDelivered: 0, StatusDeadLetter: 0}
	for rows.Next() {
		var s string
		var n int
		if err := rows.Scan(&s, &n); err != nil {
			return nil, err
		}
		out[s] = n
	}
	return out, rows.Err()
}
