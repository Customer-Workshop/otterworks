package middleware

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
)

func TestLogger_LogsRequestDetails(t *testing.T) {
	var buf bytes.Buffer
	logger := zerolog.New(&buf)

	handler := Logger(logger)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("hello"))
	}))

	req := httptest.NewRequest(http.MethodGet, "/api/v1/test?foo=bar", nil)
	req.Header.Set("User-Agent", "test-agent")
	// Set a request ID so it appears in the log
	ctx := req.Context()
	req = req.WithContext(ctx)

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code)

	logOutput := buf.String()
	assert.Contains(t, logOutput, "request completed")
	assert.Contains(t, logOutput, "/api/v1/test")
	assert.Contains(t, logOutput, "GET")
	assert.Contains(t, logOutput, "test-agent")
}

func TestLogger_Logs4xxAsWarn(t *testing.T) {
	var buf bytes.Buffer
	logger := zerolog.New(&buf)

	handler := Logger(logger)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))

	req := httptest.NewRequest(http.MethodGet, "/not-found", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusNotFound, rec.Code)
	logOutput := buf.String()
	assert.Contains(t, logOutput, `"level":"warn"`)
}

func TestLogger_Logs5xxAsError(t *testing.T) {
	var buf bytes.Buffer
	logger := zerolog.New(&buf)

	handler := Logger(logger)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))

	req := httptest.NewRequest(http.MethodPost, "/api/error", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusInternalServerError, rec.Code)
	logOutput := buf.String()
	assert.Contains(t, logOutput, `"level":"error"`)
}

func TestLogger_Logs2xxAsInfo(t *testing.T) {
	var buf bytes.Buffer
	logger := zerolog.New(&buf)

	handler := Logger(logger)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusCreated)
	}))

	req := httptest.NewRequest(http.MethodPost, "/api/v1/files", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusCreated, rec.Code)
	logOutput := buf.String()
	assert.Contains(t, logOutput, `"level":"info"`)
}

func TestSetLogLevel(t *testing.T) {
	tests := []struct {
		name  string
		level string
		want  zerolog.Level
	}{
		{"debug", "debug", zerolog.DebugLevel},
		{"info", "info", zerolog.InfoLevel},
		{"warn", "warn", zerolog.WarnLevel},
		{"error", "error", zerolog.ErrorLevel},
		{"unknown defaults to info", "unknown", zerolog.InfoLevel},
		{"empty defaults to info", "", zerolog.InfoLevel},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			SetLogLevel(tt.level)
			assert.Equal(t, tt.want, zerolog.GlobalLevel())
		})
	}

	// Reset to default
	SetLogLevel("info")
}
