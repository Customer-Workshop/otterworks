package middleware

import (
	"fmt"
	"net"
	"net/http"
	"strings"
)

// ParseTrustedProxies parses a list of CIDRs (or bare IPs) into networks.
func ParseTrustedProxies(entries []string) ([]*net.IPNet, error) {
	nets := make([]*net.IPNet, 0, len(entries))
	for _, entry := range entries {
		entry = strings.TrimSpace(entry)
		if entry == "" {
			continue
		}
		if !strings.Contains(entry, "/") {
			ip := net.ParseIP(entry)
			if ip == nil {
				return nil, fmt.Errorf("invalid trusted proxy %q", entry)
			}
			bits := 32
			if ip.To4() == nil {
				bits = 128
			}
			entry = fmt.Sprintf("%s/%d", ip, bits)
		}
		_, network, err := net.ParseCIDR(entry)
		if err != nil {
			return nil, fmt.Errorf("invalid trusted proxy %q: %w", entry, err)
		}
		nets = append(nets, network)
	}
	return nets, nil
}

// RealIP returns middleware that rewrites r.RemoteAddr to the originating client
// address, but only when the immediate peer is one of the trusted proxies. Forwarding
// headers from any other peer are ignored, so a client cannot choose its own address.
// With no trusted proxies configured, RemoteAddr is always the TCP peer.
func RealIP(trusted []*net.IPNet) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if len(trusted) > 0 && isTrusted(peerIP(r.RemoteAddr), trusted) {
				if ip := forwardedClientIP(r, trusted); ip != nil {
					r.RemoteAddr = net.JoinHostPort(ip.String(), "0")
				}
			}
			next.ServeHTTP(w, r)
		})
	}
}

func peerIP(remoteAddr string) net.IP {
	host, _, err := net.SplitHostPort(remoteAddr)
	if err != nil {
		host = remoteAddr
	}
	return net.ParseIP(strings.Trim(host, "[]"))
}

func isTrusted(ip net.IP, trusted []*net.IPNet) bool {
	if ip == nil {
		return false
	}
	for _, network := range trusted {
		if network.Contains(ip) {
			return true
		}
	}
	return false
}

// forwardedClientIP walks X-Forwarded-For from the right, skipping trusted hops, and
// returns the first address that a trusted proxy reported as its peer. X-Real-IP is
// used only when X-Forwarded-For is absent.
func forwardedClientIP(r *http.Request, trusted []*net.IPNet) net.IP {
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		parts := strings.Split(xff, ",")
		for i := len(parts) - 1; i >= 0; i-- {
			ip := net.ParseIP(strings.TrimSpace(parts[i]))
			if ip == nil {
				return nil
			}
			if !isTrusted(ip, trusted) {
				return ip
			}
		}
		return nil
	}
	if xrip := r.Header.Get("X-Real-IP"); xrip != "" {
		return net.ParseIP(strings.TrimSpace(xrip))
	}
	return nil
}
