package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func remoteAddrSeenBy(t *testing.T, trusted []string, peer string, headers map[string]string) string {
	t.Helper()
	nets, err := ParseTrustedProxies(trusted)
	require.NoError(t, err)

	var seen string
	handler := RealIP(nets)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seen = r.RemoteAddr
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	req.RemoteAddr = peer
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	handler.ServeHTTP(httptest.NewRecorder(), req)
	return seen
}

func TestRealIP_NoTrustedProxiesIgnoresForwardingHeaders(t *testing.T) {
	seen := remoteAddrSeenBy(t, nil, "203.0.113.50:4321", map[string]string{
		"X-Forwarded-For": "10.9.0.1",
		"X-Real-IP":       "10.9.0.2",
	})
	assert.Equal(t, "203.0.113.50:4321", seen)
}

func TestRealIP_UntrustedPeerCannotSpoof(t *testing.T) {
	seen := remoteAddrSeenBy(t, []string{"10.244.0.0/16"}, "203.0.113.50:4321", map[string]string{
		"X-Forwarded-For": "10.9.0.1",
	})
	assert.Equal(t, "203.0.113.50:4321", seen)
}

func TestRealIP_TrustedPeerXFF(t *testing.T) {
	seen := remoteAddrSeenBy(t, []string{"10.244.0.0/16"}, "10.244.3.7:1234", map[string]string{
		"X-Forwarded-For": "198.51.100.9",
	})
	assert.Equal(t, "198.51.100.9:0", seen)
}

func TestRealIP_TrustedPeerXRealIP(t *testing.T) {
	seen := remoteAddrSeenBy(t, []string{"10.244.0.0/16"}, "10.244.3.7:1234", map[string]string{
		"X-Real-IP": "198.51.100.9",
	})
	assert.Equal(t, "198.51.100.9:0", seen)
}

func TestRealIP_SkipsTrustedHopsFromTheRight(t *testing.T) {
	// client -> trusted hop A -> trusted hop B -> gateway; the client-supplied
	// leftmost entry must not be believed.
	seen := remoteAddrSeenBy(t, []string{"10.244.0.0/16"}, "10.244.3.7:1234", map[string]string{
		"X-Forwarded-For": "1.2.3.4, 198.51.100.9, 10.244.1.1",
	})
	assert.Equal(t, "198.51.100.9:0", seen)
}

func TestRealIP_AllHopsTrustedKeepsPeer(t *testing.T) {
	seen := remoteAddrSeenBy(t, []string{"10.244.0.0/16"}, "10.244.3.7:1234", map[string]string{
		"X-Forwarded-For": "10.244.1.1",
	})
	assert.Equal(t, "10.244.3.7:1234", seen)
}

func TestRealIP_GarbageXFFKeepsPeer(t *testing.T) {
	seen := remoteAddrSeenBy(t, []string{"10.244.0.0/16"}, "10.244.3.7:1234", map[string]string{
		"X-Forwarded-For": "not-an-ip",
	})
	assert.Equal(t, "10.244.3.7:1234", seen)
}

func TestParseTrustedProxies(t *testing.T) {
	nets, err := ParseTrustedProxies([]string{" 10.0.0.0/8 ", "192.168.1.5", "", "fd00::/8"})
	require.NoError(t, err)
	require.Len(t, nets, 3)
	assert.Equal(t, "192.168.1.5/32", nets[1].String())

	_, err = ParseTrustedProxies([]string{"nonsense"})
	assert.Error(t, err)
}

func TestRateLimiter_SpoofedForwardedForSharesBucket(t *testing.T) {
	rl := NewRateLimiter(2)
	nets, err := ParseTrustedProxies(nil)
	require.NoError(t, err)
	handler := RealIP(nets)(rl.Handler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})))

	codes := make([]int, 0, 4)
	for i := 0; i < 4; i++ {
		req := httptest.NewRequest(http.MethodGet, "/health", nil)
		req.RemoteAddr = "203.0.113.50:4321"
		req.Header.Set("X-Forwarded-For", "10.9.0."+string(rune('1'+i)))
		rec := httptest.NewRecorder()
		handler.ServeHTTP(rec, req)
		codes = append(codes, rec.Code)
	}
	assert.Equal(t, []int{200, 200, 429, 429}, codes)
}
