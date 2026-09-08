package middleware

import "testing"

func TestClassify(t *testing.T) {
	tests := []struct {
		name    string
		method  string
		path    string
		route   string
		prefix  string
		backend string
	}{
		{
			name:    "critical static route",
			method:  "POST",
			path:    "/api/v1/auth/login",
			route:   "/api/v1/auth/login",
			prefix:  "/api/v1/auth",
			backend: "auth-service",
		},
		{
			name:    "critical parameterised route",
			method:  "GET",
			path:    "/api/v1/documents/2f6b1c/export",
			route:   "/api/v1/documents/{id}/export",
			prefix:  "/api/v1/documents",
			backend: "document-service",
		},
		{
			name:    "collection and item routes stay distinct",
			method:  "GET",
			path:    "/api/v1/documents/2f6b1c",
			route:   "/api/v1/documents/{id}",
			prefix:  "/api/v1/documents",
			backend: "document-service",
		},
		{
			name:    "method not in the catalog falls back to the prefix",
			method:  "DELETE",
			path:    "/api/v1/documents/2f6b1c",
			route:   "/api/v1/documents",
			prefix:  "/api/v1/documents",
			backend: "document-service",
		},
		{
			name:    "non-critical route keeps cardinality bounded",
			method:  "GET",
			path:    "/api/v1/audit/events/9f2/details",
			route:   "/api/v1/audit",
			prefix:  "/api/v1/audit",
			backend: "audit-service",
		},
		{
			name:    "unrouted path",
			method:  "GET",
			path:    "/health",
			route:   unknownRoute,
			prefix:  unknownRoute,
			backend: unknownService,
		},
		{
			name:    "prefix match does not span a partial segment",
			method:  "GET",
			path:    "/api/v1/searchable",
			route:   unknownRoute,
			prefix:  unknownRoute,
			backend: unknownService,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			route, prefix, backend := classify(tt.method, tt.path)
			if route != tt.route || prefix != tt.prefix || backend != tt.backend {
				t.Fatalf("classify(%q, %q) = (%q, %q, %q), want (%q, %q, %q)",
					tt.method, tt.path, route, prefix, backend, tt.route, tt.prefix, tt.backend)
			}
		})
	}
}

// The route label is the SLO catalog's join key, so an unbounded identifier
// leaking into it would both break the recording rules and blow up cardinality.
func TestClassifyRouteLabelIsBounded(t *testing.T) {
	allowed := map[string]bool{unknownRoute: true}
	for _, p := range servicePrefixes {
		allowed[p.prefix] = true
	}
	for _, r := range criticalRoutes {
		allowed[r.template] = true
	}

	paths := []string{
		"/api/v1/files/9c1e-4/download",
		"/api/v1/files/9c1e-5/download",
		"/api/v1/folders/a/b/c",
		"/socket.io/?EIO=4",
		"/api/v1/collab/documents/abc/presence",
		"/metrics",
	}
	for _, path := range paths {
		route, _, _ := classify("GET", path)
		if !allowed[route] {
			t.Fatalf("classify(GET, %q) produced unbounded route label %q", path, route)
		}
	}
}
