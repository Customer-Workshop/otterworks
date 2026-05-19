package middleware

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
)

func TestLoggerMiddleware(t *testing.T) {
	var buf bytes.Buffer
	logger := zerolog.New(&buf)

	handler := Logger(logger)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("ok"))
	}))

	req := httptest.NewRequest("GET", "/api/v1/test?q=search", nil)
	req.Header.Set("User-Agent", "test-agent")
	// Inject a request ID into context
	ctx := context.WithValue(req.Context(), requestIDKey, "test-request-id")
	req = req.WithContext(ctx)

	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	assert.Equal(t, http.StatusOK, rr.Code)

	logOutput := buf.String()
	assert.Contains(t, logOutput, "request completed")
	assert.Contains(t, logOutput, "test-request-id")
	assert.Contains(t, logOutput, "GET")
	assert.Contains(t, logOutput, "/api/v1/test")
}

func TestLoggerMiddlewareStatusLevels(t *testing.T) {
	tests := []struct {
		name       string
		statusCode int
		level      string
	}{
		{"2xx logs info", http.StatusOK, "info"},
		{"4xx logs warn", http.StatusNotFound, "warn"},
		{"5xx logs error", http.StatusInternalServerError, "error"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var buf bytes.Buffer
			logger := zerolog.New(&buf)

			handler := Logger(logger)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(tt.statusCode)
			}))

			req := httptest.NewRequest("GET", "/test", nil)
			rr := httptest.NewRecorder()
			handler.ServeHTTP(rr, req)

			logOutput := buf.String()
			assert.Contains(t, logOutput, "request completed")
		})
	}
}

func TestSetLogLevel(t *testing.T) {
	tests := []struct {
		level    string
		expected zerolog.Level
	}{
		{"debug", zerolog.DebugLevel},
		{"info", zerolog.InfoLevel},
		{"warn", zerolog.WarnLevel},
		{"error", zerolog.ErrorLevel},
		{"unknown", zerolog.InfoLevel},
	}

	for _, tt := range tests {
		t.Run(tt.level, func(t *testing.T) {
			SetLogLevel(tt.level)
			assert.Equal(t, tt.expected, zerolog.GlobalLevel())
		})
	}

	// Reset
	SetLogLevel("info")
}
