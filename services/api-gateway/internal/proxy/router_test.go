package proxy

import (
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func newUnreachableRouter(t *testing.T) http.Handler {
	t.Helper()
	// Port 9 (discard) is never listening, so every proxied request fails fast.
	return NewRouter(RouterConfig{
		Routes: []Route{{Prefix: "/api/v1/files", TargetURL: "http://127.0.0.1:9"}},
		CBManager: NewCircuitBreakerManager(CircuitBreakerConfig{
			MaxRequests:  1000,
			Interval:     time.Minute,
			Timeout:      time.Minute,
			FailureRatio: 1.1, // never trips during this test
		}),
		Logger: zerolog.Nop(),
	})
}

func TestProxy_UpstreamErrorReturnsBadGatewayJSON(t *testing.T) {
	router := newUnreachableRouter(t)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/files/123", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	require.Equal(t, http.StatusBadGateway, rec.Code)
	assert.Equal(t, "application/json", rec.Header().Get("Content-Type"))
	assert.Contains(t, rec.Body.String(), `"target":"/api/v1/files"`)
	assert.Contains(t, rec.Body.String(), `"request_id"`)
}

func TestProxy_UpstreamErrorsAreCountedPerRoute(t *testing.T) {
	router := newUnreachableRouter(t)
	before := UpstreamErrorCounts()["/api/v1/files"]

	const workers = 16
	const perWorker = 8
	var wg sync.WaitGroup
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < perWorker; j++ {
				req := httptest.NewRequest(http.MethodGet, "/api/v1/files/x", nil)
				router.ServeHTTP(httptest.NewRecorder(), req)
			}
		}()
	}
	wg.Wait()

	assert.Equal(t, before+workers*perWorker, UpstreamErrorCounts()["/api/v1/files"])
}

func TestProxy_UpstreamErrorCountsSnapshotIsSafeDuringRequests(t *testing.T) {
	router := newUnreachableRouter(t)
	before := UpstreamErrorCounts()["/api/v1/files"]

	const workers = 8
	const perWorker = 16
	var wg sync.WaitGroup
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < perWorker; j++ {
				req := httptest.NewRequest(http.MethodGet, "/api/v1/files/y", nil)
				rec := httptest.NewRecorder()
				router.ServeHTTP(rec, req)
				assert.Equal(t, http.StatusBadGateway, rec.Code)
				assert.Contains(t, rec.Body.String(), `"request_id"`)
			}
		}()
	}

	// Snapshot while failures are still being recorded; every observation
	// must be monotonic and never exceed the final total.
	done := make(chan struct{})
	go func() {
		defer close(done)
		last := before
		for k := 0; k < 200; k++ {
			got := UpstreamErrorCounts()["/api/v1/files"]
			assert.GreaterOrEqual(t, got, last)
			assert.LessOrEqual(t, got, before+workers*perWorker)
			last = got
		}
	}()

	wg.Wait()
	<-done

	assert.Equal(t, before+workers*perWorker, UpstreamErrorCounts()["/api/v1/files"])
}
