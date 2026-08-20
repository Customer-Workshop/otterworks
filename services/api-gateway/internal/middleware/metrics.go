package middleware

import (
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5/middleware"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

const (
	pathAuth          = "/api/v1/auth"
	pathFiles         = "/api/v1/files"
	pathDocuments     = "/api/v1/documents"
	pathCollab        = "/api/v1/collab"
	pathNotifications = "/api/v1/notifications"
	pathSearch        = "/api/v1/search"
	pathAnalytics     = "/api/v1/analytics"
	pathAdmin         = "/api/v1/admin"
	pathAudit         = "/api/v1/audit"
)

var (
	httpRequestsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Namespace: "api_gateway",
			Name:      "http_requests_total",
			Help:      "Total number of HTTP requests.",
		},
		[]string{"method", "path", "status"},
	)

	httpRequestDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Namespace: "api_gateway",
			Name:      "http_request_duration_seconds",
			Help:      "HTTP request latency in seconds.",
			Buckets:   prometheus.DefBuckets,
		},
		[]string{"method", "path"},
	)

	httpActiveConnections = promauto.NewGauge(
		prometheus.GaugeOpts{
			Namespace: "api_gateway",
			Name:      "http_active_connections",
			Help:      "Number of active HTTP connections.",
		},
	)
)

// Metrics returns HTTP middleware that records Prometheus metrics for each request.
func Metrics(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		ww := middleware.NewWrapResponseWriter(w, r.ProtoMajor)

		httpActiveConnections.Inc()
		defer httpActiveConnections.Dec()

		next.ServeHTTP(ww, r)

		duration := time.Since(start).Seconds()
		status := strconv.Itoa(ww.Status())
		path := normalizePath(r.URL.Path)

		httpRequestsTotal.WithLabelValues(r.Method, path, status).Inc()
		httpRequestDuration.WithLabelValues(r.Method, path).Observe(duration)
	})
}

// normalizePath reduces cardinality by collapsing path parameters.
func normalizePath(path string) string {
	// Keep top-level route prefix for grouping
	switch {
	case strings.HasPrefix(path, pathAuth):
		return pathAuth
	case strings.HasPrefix(path, pathFiles):
		return pathFiles
	case strings.HasPrefix(path, pathDocuments):
		return pathDocuments
	case strings.HasPrefix(path, pathCollab):
		return pathCollab
	case strings.HasPrefix(path, pathNotifications):
		return pathNotifications
	case strings.HasPrefix(path, pathSearch):
		return pathSearch
	case strings.HasPrefix(path, pathAnalytics):
		return pathAnalytics
	case strings.HasPrefix(path, pathAdmin):
		return pathAdmin
	case strings.HasPrefix(path, pathAudit):
		return pathAudit
	default:
		return "other"
	}
}
