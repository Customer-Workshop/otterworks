package main

import (
	"context"
	"errors"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/rs/zerolog"

	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/api"
	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/config"
	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/consumer"
	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/dispatch"
	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/store"
)

func main() {
	cfg := config.Load()
	if err := cfg.Validate(); err != nil {
		l := zerolog.New(os.Stderr)
		l.Fatal().Err(err).Msg("invalid configuration")
	}
	level, err := zerolog.ParseLevel(cfg.LogLevel)
	if err != nil {
		level = zerolog.InfoLevel
	}
	log := zerolog.New(os.Stdout).Level(level).With().Timestamp().Str("service", "webhook-service").Logger()

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	var st store.Store
	if cfg.DatabaseURL == "memory" {
		st = store.NewMemory()
		log.Warn().Msg("using in-memory store; data will not persist")
	} else {
		pg := connectPostgres(ctx, cfg.DatabaseURL, log)
		defer pg.Close()
		st = pg
	}
	if err := st.Migrate(ctx); err != nil {
		log.Fatal().Err(err).Msg("migrate")
	}

	var sqsClient *sqs.Client
	if cfg.ConsumerEnabled || cfg.DeadLetterQueueURL != "" {
		opts := []func(*awsconfig.LoadOptions) error{awsconfig.WithRegion(cfg.AWSRegion)}
		if cfg.AWSEndpointURL != "" {
			opts = append(opts, awsconfig.WithCredentialsProvider(credentials.NewStaticCredentialsProvider("test", "test", "")))
		}
		awsCfg, err := awsconfig.LoadDefaultConfig(ctx, opts...)
		if err != nil {
			log.Fatal().Err(err).Msg("aws config")
		}
		sqsClient = sqs.NewFromConfig(awsCfg, func(o *sqs.Options) {
			if cfg.AWSEndpointURL != "" {
				o.BaseEndpoint = &cfg.AWSEndpointURL
			}
		})
	}

	dlq := consumer.NewDLQ(sqsClient, cfg.DeadLetterQueueURL)
	var dlqSink dispatch.DeadLetterSink
	if dlq != nil {
		dlqSink = dlq
	}
	disp := dispatch.New(st, dlqSink, dispatch.Options{
		Workers: cfg.DispatcherWorkers, PollEvery: cfg.DispatcherPollEvery, Timeout: cfg.DeliveryTimeout,
		MaxAttempts: cfg.MaxAttempts, BackoffBase: cfg.BackoffBase, BackoffMax: cfg.BackoffMax,
		AllowPrivateTargets: cfg.AllowPrivateTargets,
	}, log)
	if cfg.DispatcherEnabled {
		go disp.Run(ctx)
	}
	readiness := st.Ping
	if cfg.ConsumerEnabled {
		c := consumer.New(sqsClient, cfg.EventsQueueURL, cfg.ConsumerWaitSeconds, disp, log)
		go c.Run(ctx)
		readiness = func(ctx context.Context) error {
			if err := st.Ping(ctx); err != nil {
				return err
			}
			return c.Ready(ctx)
		}
	}

	handler := api.New(st, api.Options{
		MaxAttempts: cfg.MaxAttempts, AllowPrivateTargets: cfg.AllowPrivateTargets, Readiness: readiness,
	}, log)
	srv := &http.Server{
		Addr: ":" + cfg.Port, Handler: handler,
		ReadHeaderTimeout: 10 * time.Second, ReadTimeout: 30 * time.Second, WriteTimeout: 30 * time.Second, IdleTimeout: 120 * time.Second,
	}
	go func() {
		log.Info().Str("port", cfg.Port).Bool("consumer", cfg.ConsumerEnabled).Bool("dispatcher", cfg.DispatcherEnabled).Msg("webhook-service listening")
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatal().Err(err).Msg("http server")
		}
	}()

	<-ctx.Done()
	shutdownCtx, cancel := context.WithTimeout(context.Background(), cfg.ShutdownTimeout)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		log.Error().Err(err).Msg("shutdown")
	}
	log.Info().Msg("stopped")
}

// connectPostgres retries until the database is reachable so the container can
// start alongside postgres without depending on orchestrator ordering.
func connectPostgres(ctx context.Context, url string, log zerolog.Logger) *store.Postgres {
	const maxWait = 90 * time.Second
	deadline := time.Now().Add(maxWait)
	for {
		pg, err := store.NewPostgres(ctx, url)
		if err == nil {
			if err = pg.Ping(ctx); err == nil {
				return pg
			}
			pg.Close()
		}
		if time.Now().After(deadline) || ctx.Err() != nil {
			log.Fatal().Err(err).Msg("connect to postgres")
		}
		log.Warn().Err(err).Msg("postgres not ready, retrying")
		select {
		case <-ctx.Done():
			log.Fatal().Err(ctx.Err()).Msg("connect to postgres")
		case <-time.After(2 * time.Second):
		}
	}
}
