package config

import (
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestLoadDefaults(t *testing.T) {
	// Clear relevant env vars
	envVars := []string{"PORT", "LOG_LEVEL", "JWT_SECRET", "RATE_LIMIT_RPS"}
	saved := make(map[string]string)
	for _, k := range envVars {
		saved[k], _ = os.LookupEnv(k)
		os.Unsetenv(k)
	}
	defer func() {
		for k, v := range saved {
			if v != "" {
				os.Setenv(k, v)
			}
		}
	}()

	cfg := Load()

	assert.Equal(t, "8080", cfg.Port)
	assert.Equal(t, "info", cfg.LogLevel)
	assert.Equal(t, "", cfg.JWTSecret)
	assert.Equal(t, 100, cfg.RateLimitRPS)
	assert.Equal(t, "http://auth-service:8081", cfg.AuthServiceURL)
	assert.Equal(t, "http://file-service:8082", cfg.FileServiceURL)
	assert.Equal(t, "http://document-service:8083", cfg.DocumentServiceURL)
}

func TestLoadFromEnv(t *testing.T) {
	os.Setenv("PORT", "9090")
	os.Setenv("LOG_LEVEL", "debug")
	os.Setenv("JWT_SECRET", "test-secret")
	os.Setenv("RATE_LIMIT_RPS", "50")
	defer func() {
		os.Unsetenv("PORT")
		os.Unsetenv("LOG_LEVEL")
		os.Unsetenv("JWT_SECRET")
		os.Unsetenv("RATE_LIMIT_RPS")
	}()

	cfg := Load()

	assert.Equal(t, "9090", cfg.Port)
	assert.Equal(t, "debug", cfg.LogLevel)
	assert.Equal(t, "test-secret", cfg.JWTSecret)
	assert.Equal(t, 50, cfg.RateLimitRPS)
}

func TestValidate(t *testing.T) {
	cfg := &Config{JWTSecret: ""}
	err := cfg.Validate()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "JWT_SECRET")

	cfg.JWTSecret = "secret"
	err = cfg.Validate()
	assert.NoError(t, err)
}

func TestServiceRoutes(t *testing.T) {
	cfg := Load()
	routes := cfg.ServiceRoutes()

	assert.Contains(t, routes, "/api/v1/auth")
	assert.Contains(t, routes, "/api/v1/files")
	assert.Contains(t, routes, "/api/v1/documents")
	assert.Contains(t, routes, "/api/v1/collab")
	assert.Contains(t, routes, "/api/v1/notifications")
	assert.Contains(t, routes, "/api/v1/search")
	assert.Contains(t, routes, "/api/v1/analytics")
	assert.Contains(t, routes, "/api/v1/admin")
	assert.Contains(t, routes, "/api/v1/audit")
	assert.Contains(t, routes, "/api/v1/reports")
}

func TestCORSConfig(t *testing.T) {
	os.Setenv("CORS_ALLOWED_ORIGINS", "http://app.otterworks.io,http://admin.otterworks.io")
	defer os.Unsetenv("CORS_ALLOWED_ORIGINS")

	cfg := Load()
	assert.Equal(t, []string{"http://app.otterworks.io", "http://admin.otterworks.io"}, cfg.CORSAllowedOrigins)
}

func TestGetEnvFloat(t *testing.T) {
	os.Setenv("CB_FAILURE_RATIO", "0.75")
	defer os.Unsetenv("CB_FAILURE_RATIO")

	cfg := Load()
	assert.Equal(t, 0.75, cfg.CBFailureRatio)
}
