package config

import (
	"os"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func clearEnv(keys ...string) {
	for _, k := range keys {
		os.Unsetenv(k)
	}
}

func TestLoad_Defaults(t *testing.T) {
	clearEnv("PORT", "LOG_LEVEL", "AUTH_SERVICE_URL", "FILE_SERVICE_URL",
		"DOCUMENT_SERVICE_URL", "COLLAB_SERVICE_URL", "NOTIFICATION_SERVICE_URL",
		"SEARCH_SERVICE_URL", "ANALYTICS_SERVICE_URL", "ADMIN_SERVICE_URL",
		"AUDIT_SERVICE_URL", "REPORT_SERVICE_URL", "RATE_LIMIT_RPS", "JWT_SECRET",
		"CORS_ALLOWED_ORIGINS", "CORS_ALLOWED_METHODS", "CORS_ALLOWED_HEADERS",
		"CORS_MAX_AGE", "SHUTDOWN_TIMEOUT_SECONDS",
		"CB_MAX_REQUESTS", "CB_INTERVAL_SECONDS", "CB_TIMEOUT_SECONDS", "CB_FAILURE_RATIO")

	cfg := Load()

	assert.Equal(t, "8080", cfg.Port)
	assert.Equal(t, "info", cfg.LogLevel)
	assert.Equal(t, "http://auth-service:8081", cfg.AuthServiceURL)
	assert.Equal(t, "http://file-service:8082", cfg.FileServiceURL)
	assert.Equal(t, "http://document-service:8083", cfg.DocumentServiceURL)
	assert.Equal(t, "http://collab-service:8084", cfg.CollabServiceURL)
	assert.Equal(t, "http://notification-service:8086", cfg.NotificationServiceURL)
	assert.Equal(t, "http://search-service:8087", cfg.SearchServiceURL)
	assert.Equal(t, "http://analytics-service:8088", cfg.AnalyticsServiceURL)
	assert.Equal(t, "http://admin-service:8089", cfg.AdminServiceURL)
	assert.Equal(t, "http://audit-service:8090", cfg.AuditServiceURL)
	assert.Equal(t, "http://report-service:8091", cfg.ReportServiceURL)
	assert.Equal(t, 100, cfg.RateLimitRPS)
	assert.Equal(t, "", cfg.JWTSecret)
	assert.Equal(t, 300, cfg.CORSMaxAge)
	assert.Equal(t, 30*time.Second, cfg.ShutdownTimeout)
	assert.Equal(t, uint32(5), cfg.CBMaxRequests)
	assert.Equal(t, 60*time.Second, cfg.CBInterval)
	assert.Equal(t, 30*time.Second, cfg.CBTimeout)
	assert.InDelta(t, 0.6, cfg.CBFailureRatio, 0.001)
}

func TestLoad_CustomValues(t *testing.T) {
	os.Setenv("PORT", "9999")
	os.Setenv("LOG_LEVEL", "debug")
	os.Setenv("JWT_SECRET", "my-secret")
	os.Setenv("RATE_LIMIT_RPS", "50")
	defer clearEnv("PORT", "LOG_LEVEL", "JWT_SECRET", "RATE_LIMIT_RPS")

	cfg := Load()

	assert.Equal(t, "9999", cfg.Port)
	assert.Equal(t, "debug", cfg.LogLevel)
	assert.Equal(t, "my-secret", cfg.JWTSecret)
	assert.Equal(t, 50, cfg.RateLimitRPS)
}

func TestLoad_CORSOrigins(t *testing.T) {
	os.Setenv("CORS_ALLOWED_ORIGINS", "http://a.com,http://b.com")
	defer os.Unsetenv("CORS_ALLOWED_ORIGINS")

	cfg := Load()
	assert.Equal(t, []string{"http://a.com", "http://b.com"}, cfg.CORSAllowedOrigins)
}

func TestLoad_CORSOrigins_Default(t *testing.T) {
	os.Unsetenv("CORS_ALLOWED_ORIGINS")
	cfg := Load()
	assert.Equal(t, []string{"http://localhost:3000", "http://localhost:4200"}, cfg.CORSAllowedOrigins)
}

func TestValidate_MissingJWTSecret(t *testing.T) {
	cfg := &Config{JWTSecret: ""}
	err := cfg.Validate()
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "JWT_SECRET")
}

func TestValidate_WithJWTSecret(t *testing.T) {
	cfg := &Config{JWTSecret: "test-secret"}
	err := cfg.Validate()
	assert.NoError(t, err)
}

func TestServiceRoutes_ContainsAllPrefixes(t *testing.T) {
	cfg := Load()
	routes := cfg.ServiceRoutes()

	expectedPrefixes := []string{
		"/api/v1/auth",
		"/api/v1/files",
		"/api/v1/folders",
		"/api/v1/documents",
		"/api/v1/templates",
		"/api/v1/collab",
		"/socket.io",
		"/api/v1/notifications",
		"/api/v1/preferences",
		"/api/v1/search",
		"/api/v1/analytics",
		"/api/v1/admin",
		"/api/v1/audit",
		"/api/v1/reports",
		"/api/v1/settings",
	}

	for _, prefix := range expectedPrefixes {
		_, ok := routes[prefix]
		assert.True(t, ok, "missing route prefix: %s", prefix)
	}
	assert.Len(t, routes, len(expectedPrefixes))
}

func TestGetEnv_Fallback(t *testing.T) {
	os.Unsetenv("TEST_UNIQUE_KEY_12345")
	val := getEnv("TEST_UNIQUE_KEY_12345", "fallback")
	assert.Equal(t, "fallback", val)
}

func TestGetEnv_Set(t *testing.T) {
	os.Setenv("TEST_UNIQUE_KEY_12345", "custom")
	defer os.Unsetenv("TEST_UNIQUE_KEY_12345")
	val := getEnv("TEST_UNIQUE_KEY_12345", "fallback")
	assert.Equal(t, "custom", val)
}

func TestGetEnvInt_Fallback(t *testing.T) {
	os.Unsetenv("TEST_INT_KEY")
	val := getEnvInt("TEST_INT_KEY", 42)
	assert.Equal(t, 42, val)
}

func TestGetEnvInt_Invalid(t *testing.T) {
	os.Setenv("TEST_INT_KEY", "not-a-number")
	defer os.Unsetenv("TEST_INT_KEY")
	val := getEnvInt("TEST_INT_KEY", 42)
	assert.Equal(t, 42, val)
}

func TestGetEnvFloat_Fallback(t *testing.T) {
	os.Unsetenv("TEST_FLOAT_KEY")
	val := getEnvFloat("TEST_FLOAT_KEY", 3.14)
	assert.InDelta(t, 3.14, val, 0.001)
}

func TestGetEnvFloat_Invalid(t *testing.T) {
	os.Setenv("TEST_FLOAT_KEY", "abc")
	defer os.Unsetenv("TEST_FLOAT_KEY")
	val := getEnvFloat("TEST_FLOAT_KEY", 3.14)
	assert.InDelta(t, 3.14, val, 0.001)
}

func TestGetEnvSlice_Fallback(t *testing.T) {
	os.Unsetenv("TEST_SLICE_KEY")
	val := getEnvSlice("TEST_SLICE_KEY", []string{"a", "b"})
	assert.Equal(t, []string{"a", "b"}, val)
}

func TestGetEnvSlice_Empty(t *testing.T) {
	os.Setenv("TEST_SLICE_KEY", "")
	defer os.Unsetenv("TEST_SLICE_KEY")
	val := getEnvSlice("TEST_SLICE_KEY", []string{"a", "b"})
	assert.Equal(t, []string{"a", "b"}, val)
}

func TestGetEnvSlice_Custom(t *testing.T) {
	os.Setenv("TEST_SLICE_KEY", "x,y,z")
	defer os.Unsetenv("TEST_SLICE_KEY")
	val := getEnvSlice("TEST_SLICE_KEY", []string{"a", "b"})
	assert.Equal(t, []string{"x", "y", "z"}, val)
}
