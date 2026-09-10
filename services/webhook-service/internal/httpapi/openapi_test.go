package httpapi

import (
	"fmt"
	"net/http"
	"os"
	"strings"
	"testing"

	"github.com/go-chi/chi/v5"
	"github.com/rs/zerolog"
	"gopkg.in/yaml.v3"

	"github.com/Cognition-Partner-Workshops/otterworks/services/webhook-service/internal/store"
)

func TestOpenAPIIsReadable(t *testing.T) {
	data, err := os.ReadFile("../../openapi.yaml")
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Paths map[string]map[string]any `yaml:"paths"`
	}
	if err := yaml.Unmarshal(data, &document); err != nil {
		t.Fatal(err)
	}
	router := NewRouter(store.NewMemoryStore(), zerolog.Nop())
	routes := make(map[string]struct{})
	if err := chi.Walk(router, func(method, route string, _ http.Handler, _ ...func(http.Handler) http.Handler) error {
		routes[method+" "+route] = struct{}{}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	specRoutes := make(map[string]struct{})
	for path, methods := range document.Paths {
		for method := range methods {
			switch method {
			case "get", "post", "delete", "put", "patch", "options", "head", "trace":
				specRoutes[strings.ToUpper(method)+" "+path] = struct{}{}
			}
		}
	}
	if diff := routeDiff(routes, specRoutes); diff != "" {
		t.Fatal(diff)
	}
}

func routeDiff(actual, expected map[string]struct{}) string {
	var missing, extra []string
	for route := range expected {
		if _, ok := actual[route]; !ok {
			missing = append(missing, route)
		}
	}
	for route := range actual {
		if _, ok := expected[route]; !ok {
			extra = append(extra, route)
		}
	}
	if len(missing) == 0 && len(extra) == 0 {
		return ""
	}
	return fmt.Sprintf("route mismatch: missing=%v extra=%v", missing, extra)
}
