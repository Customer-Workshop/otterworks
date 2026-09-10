// Package dispatch fans events out to subscriptions and drives the retry /
// dead-letter lifecycle of each delivery.
package dispatch

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/rs/zerolog"

	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/events"
	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/signing"
	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/store"
)

var (
	attemptsTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "webhook_delivery_attempts_total", Help: "Delivery attempts by outcome.",
	}, []string{"outcome"})
	deadLettersTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "webhook_dead_letters_total", Help: "Deliveries that exhausted retries.",
	})
	attemptDuration = promauto.NewHistogram(prometheus.HistogramOpts{
		Name: "webhook_delivery_duration_seconds", Help: "Outbound HTTP attempt duration.",
		Buckets: prometheus.DefBuckets,
	})
)

// DeadLetterSink receives deliveries that exhausted their retries (e.g. an SQS DLQ).
type DeadLetterSink interface {
	Publish(ctx context.Context, d *store.Delivery) error
}

// Options tunes the dispatcher.
type Options struct {
	Workers             int
	PollEvery           time.Duration
	Timeout             time.Duration
	MaxAttempts         int
	BackoffBase         time.Duration
	BackoffMax          time.Duration
	AllowPrivateTargets bool
	ResponseBodyLimit   int
}

// Dispatcher owns the delivery loop.
type Dispatcher struct {
	store  store.Store
	client *http.Client
	opts   Options
	dlq    DeadLetterSink
	log    zerolog.Logger
	now    func() time.Time
}

// New builds a dispatcher. dlq may be nil.
func New(st store.Store, dlq DeadLetterSink, opts Options, log zerolog.Logger) *Dispatcher {
	if opts.Workers < 1 {
		opts.Workers = 1
	}
	if opts.PollEvery <= 0 {
		opts.PollEvery = 500 * time.Millisecond
	}
	if opts.Timeout <= 0 {
		opts.Timeout = 10 * time.Second
	}
	if opts.MaxAttempts < 1 {
		opts.MaxAttempts = 6
	}
	if opts.BackoffBase <= 0 {
		opts.BackoffBase = 2 * time.Second
	}
	if opts.BackoffMax <= 0 {
		opts.BackoffMax = 5 * time.Minute
	}
	if opts.ResponseBodyLimit <= 0 {
		opts.ResponseBodyLimit = 1024
	}
	d := &Dispatcher{
		store: st, dlq: dlq, opts: opts, log: log.With().Str("component", "dispatcher").Logger(),
		now: func() time.Time { return time.Now().UTC() },
	}
	d.client = &http.Client{
		Timeout: opts.Timeout,
		// Webhook receivers must answer directly; following redirects would let a
		// 3xx bounce the signed payload to an unexpected host.
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
		Transport:     d.transport(),
	}
	return d
}

func (d *Dispatcher) transport() http.RoundTripper {
	t := http.DefaultTransport.(*http.Transport).Clone()
	if !d.opts.AllowPrivateTargets {
		dialer := &net.Dialer{Timeout: 5 * time.Second}
		t.DialContext = func(ctx context.Context, network, addr string) (net.Conn, error) {
			host, port, err := net.SplitHostPort(addr)
			if err != nil {
				return nil, err
			}
			ips, err := net.DefaultResolver.LookupIPAddr(ctx, host)
			if err != nil {
				return nil, err
			}
			for _, ip := range ips {
				if isPrivate(ip.IP) {
					return nil, fmt.Errorf("target %s resolves to a private address", host)
				}
			}
			// Dial the literal IP just checked so no second lookup can be
			// answered differently (DNS rebinding); confirm the peer too.
			conn, err := dialer.DialContext(ctx, network, net.JoinHostPort(ips[0].IP.String(), port))
			if err != nil {
				return nil, err
			}
			if ra, ok := conn.RemoteAddr().(*net.TCPAddr); ok && isPrivate(ra.IP) {
				_ = conn.Close()
				return nil, fmt.Errorf("target %s connected to a private address", host)
			}
			return conn, nil
		}
	}
	return t
}

func isPrivate(ip net.IP) bool {
	return ip.IsLoopback() || ip.IsPrivate() || ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() || ip.IsUnspecified()
}

// ValidateTargetURL enforces the same policy at subscription time so users get
// a 400 instead of a silently dead-lettered subscription.
func ValidateTargetURL(raw string, allowPrivate bool) error {
	u, err := url.Parse(raw)
	if err != nil {
		return fmt.Errorf("invalid url: %w", err)
	}
	if u.Scheme != "http" && u.Scheme != "https" {
		return errors.New("url must use http or https")
	}
	if u.Host == "" {
		return errors.New("url must include a host")
	}
	if !allowPrivate {
		if u.Scheme != "https" {
			return errors.New("url must use https")
		}
		if ip := net.ParseIP(u.Hostname()); ip != nil && isPrivate(ip) {
			return errors.New("url must not target a private address")
		}
		if u.Hostname() == "localhost" {
			return errors.New("url must not target localhost")
		}
	}
	return nil
}

// Enqueue creates one pending delivery per active subscription that matches ev.
func (d *Dispatcher) Enqueue(ctx context.Context, ev *events.Event) (int, error) {
	if ev.OwnerID == "" {
		d.log.Warn().Str("event_id", ev.ID).Str("event_type", ev.Type).Msg("event carries no owner; not delivered")
		return 0, nil
	}
	subs, err := d.store.ActiveSubscriptionsForEvent(ctx, ev.OwnerID, ev.Type)
	if err != nil {
		return 0, err
	}
	if len(subs) == 0 {
		return 0, nil
	}
	now := d.now()
	dels := make([]*store.Delivery, 0, len(subs))
	for _, s := range subs {
		payload, err := json.Marshal(struct {
			*events.Event
			SubscriptionID string `json:"subscriptionId"`
		}{ev, s.ID})
		if err != nil {
			return 0, err
		}
		dels = append(dels, &store.Delivery{
			ID: uuid.NewString(), SubscriptionID: s.ID, OwnerID: s.OwnerID, EventID: ev.ID, EventType: ev.Type,
			Payload: payload, Status: store.StatusPending, MaxAttempts: d.opts.MaxAttempts,
			NextAttemptAt: &now, CreatedAt: now, UpdatedAt: now,
		})
	}
	return len(dels), d.store.CreateDeliveries(ctx, dels)
}

// leaseFor is how long a claimed delivery stays invisible to other workers:
// long enough for the slowest possible HTTP attempt plus bookkeeping.
func (d *Dispatcher) leaseFor() time.Duration {
	return d.opts.Timeout + 30*time.Second
}

// Run polls for due deliveries until ctx is cancelled.
func (d *Dispatcher) Run(ctx context.Context) {
	ticker := time.NewTicker(d.opts.PollEvery)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if _, err := d.RunOnce(ctx); err != nil && ctx.Err() == nil {
				d.log.Error().Err(err).Msg("dispatch cycle failed")
			}
		}
	}
}

// RunOnce claims a batch of due deliveries and attempts them concurrently.
func (d *Dispatcher) RunOnce(ctx context.Context) (int, error) {
	due, err := d.store.ClaimDueDeliveries(ctx, d.now(), d.leaseFor(), d.opts.Workers*4)
	if err != nil || len(due) == 0 {
		return 0, err
	}
	sem := make(chan struct{}, d.opts.Workers)
	var wg sync.WaitGroup
	for _, del := range due {
		wg.Add(1)
		sem <- struct{}{}
		go func(del *store.Delivery) {
			defer wg.Done()
			defer func() { <-sem }()
			if err := d.Attempt(ctx, del); err != nil {
				d.log.Error().Err(err).Str("delivery_id", del.ID).Msg("attempt bookkeeping failed")
			}
		}(del)
	}
	wg.Wait()
	return len(due), nil
}

// Attempt performs one signed POST and records the outcome.
func (d *Dispatcher) Attempt(ctx context.Context, del *store.Delivery) error {
	sub, err := d.store.GetSubscription(ctx, del.OwnerID, del.SubscriptionID)
	if err != nil {
		return err
	}
	res := store.AttemptResult{AttemptedAt: d.now()}
	attemptNo := del.Attempts + 1
	switch {
	case del.Attempts >= del.MaxAttempts:
		// Retries were already exhausted but the dead-letter publish failed last
		// time; don't hit the receiver again, just retry the publish.
		res.Error = "retries exhausted"
	case !sub.Active:
		res.Error = "subscription inactive"
	default:
		res = d.post(ctx, sub, del, res)
	}
	attemptDuration.Observe(res.Duration.Seconds())

	switch {
	case res.Success:
		attemptsTotal.WithLabelValues("delivered").Inc()
	case attemptNo >= del.MaxAttempts:
		d.deadLetter(ctx, del, &res)
	default:
		wait := Backoff(attemptNo, d.opts.BackoffBase, d.opts.BackoffMax, true)
		next := res.AttemptedAt.Add(wait)
		res.NextAttemptAt = &next
		attemptsTotal.WithLabelValues("retry").Inc()
	}

	if err := d.store.RecordAttempt(ctx, del, res); err != nil {
		return err
	}
	evt := d.log.Info()
	if !res.Success {
		evt = d.log.Warn()
	}
	evt.Str("delivery_id", del.ID).Str("subscription_id", sub.ID).Str("event_type", del.EventType).
		Int("attempt", attemptNo).Int("status_code", res.StatusCode).Str("status", del.Status).
		Str("error", res.Error).Msg("webhook attempt")

	return nil
}

// deadLetter publishes del to the DLQ sink before the row is marked
// dead_letter, so a failed publish never loses the record: the delivery stays
// retrying and the publish is re-attempted on the next due cycle.
func (d *Dispatcher) deadLetter(ctx context.Context, del *store.Delivery, res *store.AttemptResult) {
	if d.dlq != nil {
		// The DLQ record must describe the final attempt, which is not yet
		// persisted on del.
		final := *del
		if del.Attempts < del.MaxAttempts {
			final.Attempts = del.Attempts + 1
			final.LastError, final.LastStatusCode = res.Error, res.StatusCode
		}
		if err := d.dlq.Publish(ctx, &final); err != nil {
			d.log.Error().Err(err).Str("delivery_id", del.ID).Msg("failed to publish to dead-letter queue; will retry")
			next := res.AttemptedAt.Add(d.opts.BackoffBase)
			res.NextAttemptAt = &next
			res.Error = strings.TrimPrefix(res.Error+"; dead-letter publish failed: "+err.Error(), "; ")
			attemptsTotal.WithLabelValues("dead_letter_publish_failed").Inc()
			return
		}
	}
	res.DeadLetter = true
	attemptsTotal.WithLabelValues("dead_letter").Inc()
	deadLettersTotal.Inc()
}

func (d *Dispatcher) post(ctx context.Context, sub *store.Subscription, del *store.Delivery, res store.AttemptResult) store.AttemptResult {
	reqCtx, cancel := context.WithTimeout(ctx, d.opts.Timeout)
	defer cancel()
	req, err := http.NewRequestWithContext(reqCtx, http.MethodPost, sub.URL, bytes.NewReader(del.Payload))
	if err != nil {
		res.Error = err.Error()
		return res
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", "OtterWorks-Webhooks/1.0")
	req.Header.Set(signing.HeaderSignature, signing.Sign(sub.Secret, res.AttemptedAt, del.Payload))
	req.Header.Set(signing.HeaderTimestamp, fmt.Sprintf("%d", res.AttemptedAt.Unix()))
	req.Header.Set(signing.HeaderEvent, del.EventType)
	req.Header.Set(signing.HeaderEventID, del.EventID)
	req.Header.Set(signing.HeaderDeliveryID, del.ID)

	start := time.Now()
	resp, err := d.client.Do(req)
	res.Duration = time.Since(start)
	if err != nil {
		res.Error = err.Error()
		return res
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, int64(d.opts.ResponseBodyLimit)))
	res.StatusCode = resp.StatusCode
	res.ResponseBody = string(body)
	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		res.Success = true
	} else {
		res.Error = fmt.Sprintf("receiver returned HTTP %d", resp.StatusCode)
	}
	return res
}
