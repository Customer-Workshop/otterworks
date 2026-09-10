package config

import (
	"fmt"
	"os"
	"strconv"
	"time"
)

type Config struct {
	Port                string
	LogLevel            string
	DatabaseURL         string
	AWSRegion           string
	AWSEndpointURL      string
	SQSQueueURL         string
	SQSEnabled          bool
	SQSWaitTimeSeconds  int32
	DeliveryMaxAttempts int
	DeliveryBaseBackoff time.Duration
	DeliveryTimeout     time.Duration
	WorkerPollInterval  time.Duration
	DeliveryClaimLease  time.Duration
	ShutdownTimeout     time.Duration
}

func Load() Config {
	databaseURL := os.Getenv("DATABASE_URL")
	if databaseURL == "" {
		databaseURL = fmt.Sprintf("postgres://%s:%s@%s:%s/%s?sslmode=disable",
			getenv("POSTGRES_USER", "otterworks"), getenv("POSTGRES_PASSWORD", "otterworks_dev"),
			getenv("POSTGRES_HOST", "postgres"), getenv("POSTGRES_PORT", "5432"), getenv("POSTGRES_DB", "otterworks"))
	}
	return Config{
		Port:                getenv("PORT", "8092"),
		LogLevel:            getenv("LOG_LEVEL", "info"),
		DatabaseURL:         databaseURL,
		AWSRegion:           getenv("AWS_REGION", "us-east-1"),
		AWSEndpointURL:      os.Getenv("AWS_ENDPOINT_URL"),
		SQSQueueURL:         getenv("SQS_QUEUE_URL", "http://localstack:4566/000000000000/webhook-service-events"),
		SQSEnabled:          getbool("SQS_ENABLED", true),
		SQSWaitTimeSeconds:  int32(getint("SQS_WAIT_TIME_SECONDS", 10)),
		DeliveryMaxAttempts: getint("DELIVERY_MAX_ATTEMPTS", 5),
		DeliveryBaseBackoff: getduration("DELIVERY_BASE_BACKOFF", 2*time.Second),
		DeliveryTimeout:     getduration("DELIVERY_TIMEOUT", 5*time.Second),
		WorkerPollInterval:  getduration("WORKER_POLL_INTERVAL", time.Second),
		DeliveryClaimLease:  getduration("DELIVERY_CLAIM_LEASE", time.Minute),
		ShutdownTimeout:     getduration("SHUTDOWN_TIMEOUT", 30*time.Second),
	}
}

func getenv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func getint(key string, fallback int) int {
	value, err := strconv.Atoi(os.Getenv(key))
	if err != nil {
		return fallback
	}
	return value
}

func getbool(key string, fallback bool) bool {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	parsed, err := strconv.ParseBool(value)
	if err != nil {
		return fallback
	}
	return parsed
}

func getduration(key string, fallback time.Duration) time.Duration {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	parsed, err := time.ParseDuration(value)
	if err != nil {
		return fallback
	}
	return parsed
}
