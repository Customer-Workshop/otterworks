package config

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestLoadUsesDefaults(t *testing.T) {
	t.Setenv("JWT_SECRET", "")
	cfg := Load()

	assert.Equal(t, "8080", cfg.Port)
	assert.Equal(t, 100, cfg.RateLimitRPS)
	assert.Equal(t, 30*time.Second, cfg.ShutdownTimeout)
	assert.Equal(t, []string{"http://localhost:3000", "http://localhost:4200"}, cfg.CORSAllowedOrigins)
}

func TestLoadParsesEnvironmentValues(t *testing.T) {
	t.Setenv("PORT", "9090")
	t.Setenv("RATE_LIMIT_RPS", "25")
	t.Setenv("CB_FAILURE_RATIO", "0.75")
	t.Setenv("CORS_ALLOWED_ORIGINS", "https://one.example,https://two.example")

	cfg := Load()

	assert.Equal(t, "9090", cfg.Port)
	assert.Equal(t, 25, cfg.RateLimitRPS)
	assert.Equal(t, 0.75, cfg.CBFailureRatio)
	assert.Equal(t, []string{"https://one.example", "https://two.example"}, cfg.CORSAllowedOrigins)
}

func TestValidateRequiresJWTSecret(t *testing.T) {
	assert.Error(t, (&Config{}).Validate())
	assert.NoError(t, (&Config{JWTSecret: "test-secret"}).Validate())
}

func TestServiceRoutesMapsRelatedPrefixes(t *testing.T) {
	cfg := &Config{FileServiceURL: "http://files", DocumentServiceURL: "http://docs"}
	routes := cfg.ServiceRoutes()

	assert.Equal(t, "http://files", routes["/api/v1/files"])
	assert.Equal(t, "http://files", routes["/api/v1/folders"])
	assert.Equal(t, "http://docs", routes["/api/v1/documents"])
	assert.Equal(t, "http://docs", routes["/api/v1/templates"])
}
