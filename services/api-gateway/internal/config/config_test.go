package config

import "testing"

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
		{name: "strong secret accepted", secret: "a-unique-randomly-generated-secret", allowWeak: false, wantErr: false},
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
