package config

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestServiceRoutes_LegacyBillingIsOptIn(t *testing.T) {
	t.Setenv("LEGACY_BILLING_URL", "")
	routes := Load().ServiceRoutes()
	_, present := routes["/api/v1/billing"]
	assert.False(t, present)

	t.Setenv("LEGACY_BILLING_URL", "http://legacy-billing:8096")
	routes = Load().ServiceRoutes()
	assert.Equal(t, "http://legacy-billing:8096", routes["/api/v1/billing"])
}

func TestLoad_LegacyBillingURLUsesEnvironment(t *testing.T) {
	t.Setenv("LEGACY_BILLING_URL", "http://billing.test")
	assert.Equal(t, "http://billing.test", Load().LegacyBillingURL)
}
