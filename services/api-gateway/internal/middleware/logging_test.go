package middleware

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
)

func TestSetLogLevel_Debug(t *testing.T) {
	SetLogLevel("debug")
	assert.Equal(t, zerolog.DebugLevel, zerolog.GlobalLevel())
}

func TestSetLogLevel_Info(t *testing.T) {
	SetLogLevel("info")
	assert.Equal(t, zerolog.InfoLevel, zerolog.GlobalLevel())
}

func TestSetLogLevel_Warn(t *testing.T) {
	SetLogLevel("warn")
	assert.Equal(t, zerolog.WarnLevel, zerolog.GlobalLevel())
}

func TestSetLogLevel_Error(t *testing.T) {
	SetLogLevel("error")
	assert.Equal(t, zerolog.ErrorLevel, zerolog.GlobalLevel())
}

func TestSetLogLevel_Default(t *testing.T) {
	SetLogLevel("unknown-level")
	assert.Equal(t, zerolog.InfoLevel, zerolog.GlobalLevel())
}

func TestLogger_LogsRequestFields(t *testing.T) {
	var buf bytes.Buffer
	logger := zerolog.New(&buf).With().Timestamp().Logger()

	handler := Logger(logger)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("hello"))
	}))

	req := httptest.NewRequest(http.MethodGet, "/api/v1/files?q=test", nil)
	// Set request-id context via the RequestID middleware
	requestIDHandler := RequestID(handler)

	rec := httptest.NewRecorder()
	requestIDHandler.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code)
	logOutput := buf.String()
	assert.Contains(t, logOutput, "request completed")
	assert.Contains(t, logOutput, "GET")
	assert.Contains(t, logOutput, "/api/v1/files")
}

func TestLogger_LogsErrorLevel_For500(t *testing.T) {
	var buf bytes.Buffer
	logger := zerolog.New(&buf)

	handler := Logger(logger)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))

	req := httptest.NewRequest(http.MethodGet, "/fail", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusInternalServerError, rec.Code)
	logOutput := buf.String()
	assert.Contains(t, logOutput, `"level":"error"`)
}

func TestLogger_LogsWarnLevel_For400(t *testing.T) {
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
