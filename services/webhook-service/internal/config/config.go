package config

import (
	"fmt"
	"os"
	"strconv"
	"time"
)

// Config holds all configuration for the webhook service.
type Config struct {
	Port     string
	LogLevel string

	DatabaseURL string

	AWSRegion           string
	AWSEndpointURL      string
	EventsQueueURL      string
	DeadLetterQueueURL  string
	ConsumerEnabled     bool
	ConsumerWaitSeconds int32

	DispatcherEnabled   bool
	DispatcherWorkers   int
	DispatcherPollEvery time.Duration
	DeliveryTimeout     time.Duration
	MaxAttempts         int
	BackoffBase         time.Duration
	BackoffMax          time.Duration

	// AllowPrivateTargets permits webhook targets that resolve to loopback /
	// private ranges. Required for the localhost demo; keep false elsewhere.
	AllowPrivateTargets bool

	ShutdownTimeout time.Duration
}

// Load reads configuration from environment variables with sensible defaults.
func Load() *Config {
	return &Config{
		Port:     getEnv("PORT", "8092"),
		LogLevel: getEnv("LOG_LEVEL", "info"),

		DatabaseURL: getEnv("DATABASE_URL", buildPostgresURL()),

		AWSRegion:           getEnv("AWS_REGION", "us-east-1"),
		AWSEndpointURL:      getEnv("AWS_ENDPOINT_URL", ""),
		EventsQueueURL:      getEnv("WEBHOOK_EVENTS_QUEUE_URL", ""),
		DeadLetterQueueURL:  getEnv("WEBHOOK_DLQ_URL", ""),
		ConsumerEnabled:     getEnvBool("CONSUMER_ENABLED", true),
		ConsumerWaitSeconds: int32(getEnvInt("CONSUMER_WAIT_SECONDS", 10)),

		DispatcherEnabled:   getEnvBool("DISPATCHER_ENABLED", true),
		DispatcherWorkers:   getEnvInt("DISPATCHER_WORKERS", 4),
		DispatcherPollEvery: time.Duration(getEnvInt("DISPATCHER_POLL_MS", 500)) * time.Millisecond,
		DeliveryTimeout:     time.Duration(getEnvInt("DELIVERY_TIMEOUT_SECONDS", 10)) * time.Second,
		MaxAttempts:         getEnvInt("DELIVERY_MAX_ATTEMPTS", 6),
		BackoffBase:         time.Duration(getEnvInt("DELIVERY_BACKOFF_BASE_MS", 2000)) * time.Millisecond,
		BackoffMax:          time.Duration(getEnvInt("DELIVERY_BACKOFF_MAX_SECONDS", 300)) * time.Second,

		AllowPrivateTargets: getEnvBool("ALLOW_PRIVATE_TARGETS", false),

		ShutdownTimeout: time.Duration(getEnvInt("SHUTDOWN_TIMEOUT_SECONDS", 20)) * time.Second,
	}
}

// Validate checks required configuration.
func (c *Config) Validate() error {
	if c.DatabaseURL == "" {
		return fmt.Errorf("DATABASE_URL (or POSTGRES_* variables) is required")
	}
	if c.ConsumerEnabled && c.EventsQueueURL == "" {
		return fmt.Errorf("WEBHOOK_EVENTS_QUEUE_URL is required when CONSUMER_ENABLED=true")
	}
	if c.MaxAttempts < 1 {
		return fmt.Errorf("DELIVERY_MAX_ATTEMPTS must be >= 1")
	}
	return nil
}

func buildPostgresURL() string {
	host := os.Getenv("POSTGRES_HOST")
	if host == "" {
		return ""
	}
	return fmt.Sprintf("postgres://%s:%s@%s:%s/%s?sslmode=disable",
		getEnv("POSTGRES_USER", "otterworks"),
		getEnv("POSTGRES_PASSWORD", "otterworks_dev"),
		host,
		getEnv("POSTGRES_PORT", "5432"),
		getEnv("POSTGRES_DB", "otterworks"),
	)
}

func getEnv(key, fallback string) string {
	if val, ok := os.LookupEnv(key); ok {
		return val
	}
	return fallback
}

func getEnvInt(key string, fallback int) int {
	if val, ok := os.LookupEnv(key); ok {
		if i, err := strconv.Atoi(val); err == nil {
			return i
		}
	}
	return fallback
}

func getEnvBool(key string, fallback bool) bool {
	if val, ok := os.LookupEnv(key); ok {
		if b, err := strconv.ParseBool(val); err == nil {
			return b
		}
	}
	return fallback
}
