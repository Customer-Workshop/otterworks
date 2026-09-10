package targets

import "testing"

func TestValidate(t *testing.T) {
	for _, test := range []struct {
		name         string
		rawURL       string
		allowPrivate bool
		wantErr      bool
	}{
		{name: "public IP", rawURL: "https://1.1.1.1/hook"},
		{name: "loopback", rawURL: "http://127.0.0.1/hook", wantErr: true},
		{name: "private", rawURL: "http://10.0.0.1/hook", wantErr: true},
		{name: "link local", rawURL: "http://169.254.1.1/hook", wantErr: true},
		{name: "ipv6 loopback", rawURL: "http://[::1]/hook", wantErr: true},
		{name: "localhost", rawURL: "http://localhost/hook", wantErr: true},
		{name: "allowed private", rawURL: "http://127.0.0.1/hook", allowPrivate: true},
	} {
		t.Run(test.name, func(t *testing.T) {
			if err := Validate(test.rawURL, test.allowPrivate); (err != nil) != test.wantErr {
				t.Fatalf("Validate(%q) error=%v, wantErr=%v", test.rawURL, err, test.wantErr)
			}
		})
	}
}
