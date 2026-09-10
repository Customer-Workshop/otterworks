package main

import (
	"context"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/config"
	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/consumer"
	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/delivery"
	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/httpapi"
	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/store"
	"github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
)

func main() {
	cfg := config.Load()
	logger := zerolog.New(os.Stdout).With().Timestamp().Str("service", "webhook-service").Logger()
	ctx := context.Background()
	db, err := store.NewPostgresStore(ctx, cfg.DatabaseURL, cfg.DeliveryClaimLease)
	if err != nil {
		logger.Fatal().Err(err).Msg("initialize store")
	}
	defer db.Close()
	sqsClient := newSQSClient(ctx, cfg)
	runCtx, cancel := signal.NotifyContext(ctx, syscall.SIGINT, syscall.SIGTERM)
	defer cancel()
	if cfg.SQSEnabled {
		go consumer.New(sqsClient, cfg.SQSQueueURL, db, logger, cfg.SQSWaitTimeSeconds, cfg.DeliveryMaxAttempts).Run(runCtx)
	}
	go delivery.NewWorker(db, &http.Client{Timeout: cfg.DeliveryTimeout}, cfg.WorkerPollInterval, cfg.DeliveryBaseBackoff, logger).Run(runCtx)
	server := &http.Server{
		Addr:         ":" + cfg.Port,
		Handler:      httpapi.NewRouter(db, logger, cfg.DeliveryMaxAttempts),
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  60 * time.Second,
	}
	go func() {
		logger.Info().Str("port", cfg.Port).Msg("webhook service listening")
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Fatal().Err(err).Msg("server failed")
		}
	}()
	<-runCtx.Done()
	shutdownCtx, cancelShutdown := context.WithTimeout(context.Background(), cfg.ShutdownTimeout)
	defer cancelShutdown()
	_ = server.Shutdown(shutdownCtx)
}
func newSQSClient(ctx context.Context, cfg config.Config) *sqs.Client {
	loadOpts := []func(*awsconfig.LoadOptions) error{awsconfig.WithRegion(cfg.AWSRegion)}
	awsCfg, err := awsconfig.LoadDefaultConfig(ctx, loadOpts...)
	if err != nil {
		log.Fatal().Err(err).Msg("load AWS config")
	}
	return sqs.NewFromConfig(awsCfg, func(o *sqs.Options) {
		if cfg.AWSEndpointURL != "" {
			o.BaseEndpoint = aws.String(cfg.AWSEndpointURL)
		}
	})
}
