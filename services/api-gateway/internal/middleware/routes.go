package middleware

import "strings"

// routePattern is a gateway route template. Segments wrapped in braces in the
// template match any single path segment.
type routePattern struct {
	method   string
	template string
	service  string

	segments []string
}

// servicePrefix maps a gateway route prefix to the backend that serves it.
// Requests that are not part of the SLO catalog are labelled with their prefix,
// which keeps the metric cardinality bounded while still attributing traffic to
// a service. Keep in sync with config.ServiceRoutes.
type servicePrefix struct {
	prefix  string
	service string
}

var servicePrefixes = []servicePrefix{
	{"/api/v1/auth", "auth-service"},
	{"/api/v1/settings", "auth-service"},
	{"/api/v1/files", "file-service"},
	{"/api/v1/folders", "file-service"},
	{"/api/v1/documents", "document-service"},
	{"/api/v1/templates", "document-service"},
	{"/api/v1/collab", "collab-service"},
	{"/socket.io", "collab-service"},
	{"/api/v1/notifications", "notification-service"},
	{"/api/v1/preferences", "notification-service"},
	{"/api/v1/search", "search-service"},
	{"/api/v1/analytics", "analytics-service"},
	{"/api/v1/admin", "admin-service"},
	{"/api/v1/audit", "audit-service"},
	{"/api/v1/reports", "report-service"},
}

const (
	unknownRoute   = "other"
	unknownService = "unknown"
)

func init() {
	for i := range criticalRoutes {
		criticalRoutes[i].segments = splitPath(criticalRoutes[i].template)
	}
}

// classify resolves a request to the metric labels it is recorded under: the
// route template when the request hits an endpoint in the SLO catalog, and the
// service prefix otherwise.
func classify(method, path string) (route, prefix, backend string) {
	prefix, backend = matchPrefix(path)

	segments := splitPath(path)
	for i := range criticalRoutes {
		if criticalRoutes[i].matches(method, segments) {
			return criticalRoutes[i].template, prefix, criticalRoutes[i].service
		}
	}
	return prefix, prefix, backend
}

func (p routePattern) matches(method string, segments []string) bool {
	if p.method != method || len(p.segments) != len(segments) {
		return false
	}
	for i, want := range p.segments {
		if isParam(want) {
			continue
		}
		if want != segments[i] {
			return false
		}
	}
	return true
}

func matchPrefix(path string) (prefix, backend string) {
	for _, candidate := range servicePrefixes {
		if path == candidate.prefix || strings.HasPrefix(path, candidate.prefix+"/") {
			return candidate.prefix, candidate.service
		}
	}
	return unknownRoute, unknownService
}

func splitPath(path string) []string {
	trimmed := strings.Trim(path, "/")
	if trimmed == "" {
		return nil
	}
	return strings.Split(trimmed, "/")
}

func isParam(segment string) bool {
	return len(segment) >= 2 && segment[0] == '{' && segment[len(segment)-1] == '}'
}
