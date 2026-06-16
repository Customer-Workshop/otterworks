package config

import (
	"strings"
	"testing"
)

func TestValidate(t *testing.T) {
	tests := []struct {
		name      string
		secret    string
		allowWeak bool
		wantErr   bool
	}{
		{name: "empty secret rejected", secret: "", allowWeak: false, wantErr: true},
		{name: "default secret rejected", secret: insecureDefaultJWTSecret, allowWeak: false, wantErr: true},
		{name: "default secret allowed in dev", secret: insecureDefaultJWTSecret, allowWeak: true, wantErr: false},
		// Built at runtime so the test fixture itself is not a hardcoded secret.
		{name: "strong secret accepted", secret: strings.Repeat("x", 48), allowWeak: false, wantErr: false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			c := &Config{JWTSecret: tt.secret, AllowInsecureJWTSecret: tt.allowWeak}
			err := c.Validate()
			if (err != nil) != tt.wantErr {
				t.Fatalf("Validate() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}
