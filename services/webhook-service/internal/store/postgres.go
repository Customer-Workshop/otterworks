package store

import (
	"context"
	"strconv"
	"strings"
	"time"

	"github.com/golang-migrate/migrate/v4"
	_ "github.com/golang-migrate/migrate/v4/database/postgres"
	"github.com/golang-migrate/migrate/v4/source/iofs"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type PostgresStore struct {
	pool       *pgxpool.Pool
	ClaimLease time.Duration
}

func NewPostgresStore(ctx context.Context, dsn string, lease ...time.Duration) (*PostgresStore, error) {
	claimLease := time.Minute
	if len(lease) > 0 && lease[0] > 0 {
		claimLease = lease[0]
	}
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		return nil, err
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, err
	}
	if _, err := pool.Exec(ctx, `CREATE SCHEMA IF NOT EXISTS webhook`); err != nil {
		pool.Close()
		return nil, err
	}
	source, err := iofs.New(MigrationFS, "migrations")
	if err != nil {
		pool.Close()
		return nil, err
	}
	m, err := migrate.NewWithSourceInstance("iofs", source, migrationDSN(dsn))
	if err != nil {
		pool.Close()
		return nil, err
	}
	if err = m.Up(); err != nil && err != migrate.ErrNoChange {
		m.Close()
		pool.Close()
		return nil, err
	}
	m.Close()
	return &PostgresStore{pool: pool, ClaimLease: claimLease}, nil
}

func migrationDSN(dsn string) string {
	separator := "?"
	if strings.Contains(dsn, "?") {
		separator = "&"
	}
	return dsn + separator + "search_path=webhook&x-migrations-table=schema_migrations"
}
func (s *PostgresStore) Close() { s.pool.Close() }
func (s *PostgresStore) CreateSubscription(ctx context.Context, sub *Subscription) error {
	_, err := s.pool.Exec(ctx, `INSERT INTO webhook.subscriptions (id,owner_id,target_url,event_types,description,secret,active,created_at,updated_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$8)`, sub.ID, sub.OwnerID, sub.TargetURL, sub.EventTypes, sub.Description, sub.Secret, sub.Active, sub.CreatedAt)
	return err
}
func (s *PostgresStore) ListSubscriptions(ctx context.Context, owner string) ([]Subscription, error) {
	rows, err := s.pool.Query(ctx, `SELECT id,owner_id,target_url,event_types,description,secret,active,created_at,updated_at FROM webhook.subscriptions WHERE owner_id=$1 ORDER BY created_at DESC`, owner)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Subscription
	for rows.Next() {
		var item Subscription
		if err := rows.Scan(&item.ID, &item.OwnerID, &item.TargetURL, &item.EventTypes, &item.Description, &item.Secret, &item.Active, &item.CreatedAt, &item.UpdatedAt); err != nil {
			return nil, err
		}
		out = append(out, item)
	}
	return out, rows.Err()
}
func (s *PostgresStore) GetSubscription(ctx context.Context, owner string, id uuid.UUID) (*Subscription, error) {
	var item Subscription
	err := s.pool.QueryRow(ctx, `SELECT id,owner_id,target_url,event_types,description,secret,active,created_at,updated_at FROM webhook.subscriptions WHERE owner_id=$1 AND id=$2`, owner, id).Scan(&item.ID, &item.OwnerID, &item.TargetURL, &item.EventTypes, &item.Description, &item.Secret, &item.Active, &item.CreatedAt, &item.UpdatedAt)
	if err == pgx.ErrNoRows {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	return &item, nil
}
func (s *PostgresStore) DeleteSubscription(ctx context.Context, owner string, id uuid.UUID) error {
	tag, err := s.pool.Exec(ctx, `DELETE FROM webhook.subscriptions WHERE owner_id=$1 AND id=$2`, owner, id)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}
func (s *PostgresStore) ListActiveSubscriptionsForEvent(ctx context.Context, event string) ([]Subscription, error) {
	rows, err := s.pool.Query(ctx, `SELECT id,owner_id,target_url,event_types,description,secret,active,created_at,updated_at FROM webhook.subscriptions WHERE active AND $1=ANY(event_types)`, event)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Subscription
	for rows.Next() {
		var item Subscription
		if err := rows.Scan(&item.ID, &item.OwnerID, &item.TargetURL, &item.EventTypes, &item.Description, &item.Secret, &item.Active, &item.CreatedAt, &item.UpdatedAt); err != nil {
			return nil, err
		}
		out = append(out, item)
	}
	return out, rows.Err()
}
func (s *PostgresStore) EnqueueDelivery(ctx context.Context, d *Delivery) error {
	if d.MaxAttempts <= 0 {
		d.MaxAttempts = 5
	}
	_, err := s.pool.Exec(ctx, `INSERT INTO webhook.deliveries (id,subscription_id,event_type,payload,status,attempts,max_attempts,next_attempt_at,created_at,updated_at,source_message_id) VALUES ($1,$2,$3,$4,'pending',0,$5,$6,$7,$7,$8) ON CONFLICT (subscription_id, source_message_id) WHERE source_message_id IS NOT NULL DO NOTHING`, d.ID, d.SubscriptionID, d.EventType, d.Payload, d.MaxAttempts, d.NextAttemptAt, d.CreatedAt, d.SourceMessageID)
	return err
}
func (s *PostgresStore) ListDeliveries(ctx context.Context, owner string, subID *uuid.UUID, limit int) ([]Delivery, error) {
	query := `SELECT d.id,d.subscription_id,d.event_type,d.payload,d.status,d.attempts,d.max_attempts,d.last_response_code,d.last_error,d.next_attempt_at,d.created_at,d.updated_at,d.delivered_at,s.target_url,s.secret,d.source_message_id FROM webhook.deliveries d JOIN webhook.subscriptions s ON s.id=d.subscription_id WHERE s.owner_id=$1`
	args := []any{owner}
	if subID != nil {
		query += " AND d.subscription_id=$2"
		args = append(args, *subID)
	}
	query += " ORDER BY d.created_at DESC LIMIT $" + strconv.Itoa(len(args)+1)
	args = append(args, limit)
	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Delivery
	for rows.Next() {
		var d Delivery
		if err := rows.Scan(&d.ID, &d.SubscriptionID, &d.EventType, &d.Payload, &d.Status, &d.Attempts, &d.MaxAttempts, &d.LastResponseCode, &d.LastError, &d.NextAttemptAt, &d.CreatedAt, &d.UpdatedAt, &d.DeliveredAt, &d.TargetURL, &d.Secret, &d.SourceMessageID); err != nil {
			return nil, err
		}
		d.AttemptsLog, err = s.attempts(ctx, d.ID)
		if err != nil {
			return nil, err
		}
		out = append(out, d)
	}
	return out, rows.Err()
}
func (s *PostgresStore) attempts(ctx context.Context, id uuid.UUID) ([]DeliveryAttempt, error) {
	rows, err := s.pool.Query(ctx, `SELECT id,delivery_id,attempt,response_code,error,duration_ms,attempted_at FROM webhook.delivery_attempts WHERE delivery_id=$1 ORDER BY attempt`, id)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []DeliveryAttempt
	for rows.Next() {
		var a DeliveryAttempt
		if err := rows.Scan(&a.ID, &a.DeliveryID, &a.Attempt, &a.ResponseCode, &a.Error, &a.DurationMS, &a.AttemptedAt); err != nil {
			return nil, err
		}
		out = append(out, a)
	}
	return out, rows.Err()
}
func (s *PostgresStore) ClaimDueDeliveries(ctx context.Context, limit int) ([]Delivery, error) {
	rows, err := s.pool.Query(ctx, `WITH due AS (
		SELECT id
		FROM webhook.deliveries
		WHERE status='pending' AND next_attempt_at<=now()
		ORDER BY next_attempt_at
		LIMIT $1
		FOR UPDATE SKIP LOCKED
	)
	UPDATE webhook.deliveries d
	SET next_attempt_at=now()+$2::interval, updated_at=now()
	FROM due
	WHERE d.id=due.id
	RETURNING d.id`, limit, s.ClaimLease.String())
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var ids []uuid.UUID
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	if len(ids) == 0 {
		return nil, nil
	}
	deliveryRows, err := s.pool.Query(ctx, `SELECT d.id,d.subscription_id,d.event_type,d.payload,d.status,d.attempts,d.max_attempts,d.last_response_code,d.last_error,d.next_attempt_at,d.created_at,d.updated_at,d.delivered_at,s.target_url,s.secret,d.source_message_id
		FROM webhook.deliveries d
		JOIN webhook.subscriptions s ON s.id=d.subscription_id
		WHERE d.id=ANY($1)`, ids)
	if err != nil {
		return nil, err
	}
	defer deliveryRows.Close()
	out := make([]Delivery, 0, len(ids))
	for deliveryRows.Next() {
		var d Delivery
		if err := deliveryRows.Scan(&d.ID, &d.SubscriptionID, &d.EventType, &d.Payload, &d.Status, &d.Attempts, &d.MaxAttempts, &d.LastResponseCode, &d.LastError, &d.NextAttemptAt, &d.CreatedAt, &d.UpdatedAt, &d.DeliveredAt, &d.TargetURL, &d.Secret, &d.SourceMessageID); err != nil {
			return nil, err
		}
		out = append(out, d)
	}
	return out, deliveryRows.Err()
}
func (s *PostgresStore) RecordAttempt(ctx context.Context, a *DeliveryAttempt) error {
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(ctx, `INSERT INTO webhook.delivery_attempts (id,delivery_id,attempt,response_code,error,duration_ms,attempted_at) VALUES ($1,$2,$3,$4,$5,$6,$7)`, a.ID, a.DeliveryID, a.Attempt, a.ResponseCode, a.Error, a.DurationMS, a.AttemptedAt); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `UPDATE webhook.deliveries SET attempts=$2,last_response_code=$3,last_error=$4,updated_at=now() WHERE id=$1`, a.DeliveryID, a.Attempt, a.ResponseCode, a.Error); err != nil {
		return err
	}
	return tx.Commit(ctx)
}
func (s *PostgresStore) MarkDelivered(ctx context.Context, id uuid.UUID, at time.Time) error {
	_, err := s.pool.Exec(ctx, `UPDATE webhook.deliveries SET status='delivered',delivered_at=$2,updated_at=$2 WHERE id=$1`, id, at)
	return err
}
func (s *PostgresStore) MarkRetry(ctx context.Context, id uuid.UUID, at time.Time) error {
	_, err := s.pool.Exec(ctx, `UPDATE webhook.deliveries SET status='pending',next_attempt_at=$2,updated_at=now() WHERE id=$1`, id, at)
	return err
}
func (s *PostgresStore) MarkFailed(ctx context.Context, id uuid.UUID) error {
	_, err := s.pool.Exec(ctx, `UPDATE webhook.deliveries SET status='failed',updated_at=now() WHERE id=$1`, id)
	return err
}
