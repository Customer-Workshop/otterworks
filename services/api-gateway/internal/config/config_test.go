package config

import "testing"

func TestValidate_EmptySecret(t *testing.T) {
	c := &Config{JWTSecret: ""}
	if err := c.Validate(); err == nil {
		t.Fatal("expected error for empty JWT_SECRET")
	}
}

func TestValidate_DefaultDevSecret(t *testing.T) {
	c := &Config{JWTSecret: "otterworks-local-dev-jwt-secret-change-me-in-production"}
	if err := c.Validate(); err == nil {
		t.Fatal("expected error for default dev secret")
	}
}

func TestValidate_ShortSecret(t *testing.T) {
	c := &Config{JWTSecret: "short-secret"}
	if err := c.Validate(); err == nil {
		t.Fatal("expected error for short secret")
	}
}

func TestValidate_ValidSecret(t *testing.T) {
	c := &Config{JWTSecret: "a-very-long-secret-that-is-at-least-32-characters-long"}
	if err := c.Validate(); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}
