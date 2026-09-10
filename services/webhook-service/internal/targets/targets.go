package targets

import (
	"context"
	"fmt"
	"net"
	"net/url"
	"strings"
	"time"
)

func Validate(rawURL string, allowPrivate bool) error {
	parsed, err := url.Parse(rawURL)
	if err != nil || parsed.Host == "" || (parsed.Scheme != "http" && parsed.Scheme != "https") {
		return fmt.Errorf("target_url must be a valid http or https URL")
	}
	if allowPrivate {
		return nil
	}
	host := strings.TrimSuffix(strings.ToLower(parsed.Hostname()), ".")
	if host == "localhost" || strings.HasSuffix(host, ".localhost") {
		return fmt.Errorf("target_url must not point to localhost")
	}
	if ip := net.ParseIP(host); ip != nil {
		if blockedIP(ip) {
			return fmt.Errorf("target_url must not point to a private or local address")
		}
		return nil
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	ips, err := net.DefaultResolver.LookupIPAddr(ctx, host)
	if err != nil {
		return fmt.Errorf("target_url host could not be resolved")
	}
	if len(ips) == 0 {
		return fmt.Errorf("target_url host could not be resolved")
	}
	for _, resolved := range ips {
		if blockedIP(resolved.IP) {
			return fmt.Errorf("target_url must not resolve to a private or local address")
		}
	}
	return nil
}

func BlockedIP(ip net.IP) bool {
	return blockedIP(ip)
}

func blockedIP(ip net.IP) bool {
	return ip.IsLoopback() || ip.IsPrivate() || ip.IsLinkLocalUnicast() ||
		ip.IsUnspecified() || ip.IsMulticast() ||
		ip.Equal(net.ParseIP("169.254.169.254"))
}
