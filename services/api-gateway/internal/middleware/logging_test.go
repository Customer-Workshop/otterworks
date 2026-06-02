package middleware

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
)

func TestLogger_LogsRequest(t *testing.T) {
	var buf bytes.Buffer
	logger := zerolog.New(&buf).With().Timestamp().Logger()

	handler := Logger(logger)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("ok"))
	}))

	req := httptest.NewRequest(http.MethodGet, "/api/test?q=1", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code)

	logOutput := buf.String()
	assert.Contains(t, logOutput, "request completed")
	assert.Contains(t, logOutput, "/api/test")
	assert.Contains(t, logOutput, "GET")
}

func TestLogger_500UsesErrorLevel(t *testing.T) {
	var buf bytes.Buffer
	logger := zerolog.New(&buf)

	handler := Logger(logger)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))

	req := httptest.NewRequest(http.MethodPost, "/fail", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusInternalServerError, rec.Code)
	logOutput := buf.String()
	assert.Contains(t, logOutput, `"level":"error"`)
}

func TestLogger_400UsesWarnLevel(t *testing.T) {
	var buf bytes.Buffer
	logger := zerolog.New(&buf)

	handler := Logger(logger)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
	}))

	req := httptest.NewRequest(http.MethodGet, "/bad", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusBadRequest, rec.Code)
	logOutput := buf.String()
	assert.Contains(t, logOutput, `"level":"warn"`)
}

func TestLogger_200UsesInfoLevel(t *testing.T) {
	var buf bytes.Buffer
	logger := zerolog.New(&buf)

	handler := Logger(logger)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodGet, "/ok", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	logOutput := buf.String()
	assert.Contains(t, logOutput, `"level":"info"`)
}

func TestSetLogLevel_ValidLevels(t *testing.T) {
	levels := []string{"debug", "info", "warn", "error"}
	for _, level := range levels {
		SetLogLevel(level)
	}
	// Just verify no panic occurs for all valid levels
}

func TestSetLogLevel_UnknownDefaultsToInfo(t *testing.T) {
	SetLogLevel("unknown")
	assert.Equal(t, zerolog.InfoLevel, zerolog.GlobalLevel())
}
