package main

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/go-chi/chi/v5"
	chimw "github.com/go-chi/chi/v5/middleware"
	"github.com/go-chi/cors"
	"github.com/go-chi/httprate"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
)

type Config struct {
	Port                  string
	AuthServiceURL        string
	FileServiceURL        string
	DocumentServiceURL    string
	CollabServiceURL      string
	NotificationServiceURL string
	SearchServiceURL      string
	AnalyticsServiceURL   string
	AdminServiceURL       string
	AuditServiceURL       string
}

func loadConfig() Config {
	return Config{
		Port:                  getEnv("PORT", "8080"),
		AuthServiceURL:        getEnv("AUTH_SERVICE_URL", "http://localhost:8081"),
		FileServiceURL:        getEnv("FILE_SERVICE_URL", "http://localhost:8082"),
		DocumentServiceURL:    getEnv("DOCUMENT_SERVICE_URL", "http://localhost:8083"),
		CollabServiceURL:      getEnv("COLLAB_SERVICE_URL", "http://localhost:8084"),
		NotificationServiceURL: getEnv("NOTIFICATION_SERVICE_URL", "http://localhost:8086"),
		SearchServiceURL:      getEnv("SEARCH_SERVICE_URL", "http://localhost:8087"),
		AnalyticsServiceURL:   getEnv("ANALYTICS_SERVICE_URL", "http://localhost:8088"),
		AdminServiceURL:       getEnv("ADMIN_SERVICE_URL", "http://localhost:8089"),
		AuditServiceURL:       getEnv("AUDIT_SERVICE_URL", "http://localhost:8090"),
	}
}

func getEnv(key, fallback string) string {
	if val, ok := os.LookupEnv(key); ok {
		return val
	}
	return fallback
}

func newReverseProxy(target string) http.Handler {
	u, err := url.Parse(target)
	if err != nil {
		log.Fatal().Err(err).Str("target", target).Msg("invalid proxy target URL")
	}
	proxy := httputil.NewSingleHostReverseProxy(u)
	proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		log.Error().Err(err).Str("target", target).Str("path", r.URL.Path).Msg("proxy error")
		w.WriteHeader(http.StatusBadGateway)
		fmt.Fprintf(w, `{"error":"service unavailable","target":"%s"}`, target)
	}
	return proxy
}

func requestLogger(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		ww := chimw.NewWrapResponseWriter(w, r.ProtoMajor)
		next.ServeHTTP(ww, r)
		log.Info().
			Str("method", r.Method).
			Str("path", r.URL.Path).
			Int("status", ww.Status()).
			Dur("latency", time.Since(start)).
			Str("remote", r.RemoteAddr).
			Str("user_agent", r.UserAgent()).
			Msg("request")
	})
}

func main() {
	// Structured JSON logging
	zerolog.TimeFieldFormat = zerolog.TimeFormatUnix
	log.Logger = zerolog.New(os.Stdout).With().Timestamp().Str("service", "api-gateway").Logger()

	cfg := loadConfig()

	r := chi.NewRouter()

	// --- Middleware ---
	r.Use(chimw.RequestID)
	r.Use(chimw.RealIP)
	r.Use(requestLogger)
	r.Use(chimw.Recoverer)
	r.Use(chimw.Compress(5))
	r.Use(httprate.LimitByIP(100, time.Minute))
	r.Use(cors.Handler(cors.Options{
		AllowedOrigins:   []string{"http://localhost:3000", "http://localhost:4200"},
		AllowedMethods:   []string{"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"},
		AllowedHeaders:   []string{"Accept", "Authorization", "Content-Type", "X-Request-ID"},
		ExposedHeaders:   []string{"Link", "X-Request-ID"},
		AllowCredentials: true,
		MaxAge:           300,
	}))

	// --- Health Check ---
	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		fmt.Fprint(w, `{"status":"healthy","service":"api-gateway"}`)
	})

	// --- Metrics ---
	r.Get("/metrics", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		fmt.Fprint(w, "# HELP api_gateway_up API Gateway is running\n# TYPE api_gateway_up gauge\napi_gateway_up 1\n")
	})

	// --- Route Proxies ---
	r.Route("/api/v1", func(r chi.Router) {
		r.Mount("/auth", newReverseProxy(cfg.AuthServiceURL))
		r.Mount("/files", newReverseProxy(cfg.FileServiceURL))
		r.Mount("/documents", newReverseProxy(cfg.DocumentServiceURL))
		r.Mount("/collab", newReverseProxy(cfg.CollabServiceURL))
		r.Mount("/notifications", newReverseProxy(cfg.NotificationServiceURL))
		r.Mount("/search", newReverseProxy(cfg.SearchServiceURL))
		r.Mount("/analytics", newReverseProxy(cfg.AnalyticsServiceURL))
		r.Mount("/admin", newReverseProxy(cfg.AdminServiceURL))
		r.Mount("/audit", newReverseProxy(cfg.AuditServiceURL))
	})

	// --- Server ---
	srv := &http.Server{
		Addr:         ":" + cfg.Port,
		Handler:      r,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// Graceful shutdown
	go func() {
		log.Info().Str("port", cfg.Port).Msg("API Gateway starting")
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatal().Err(err).Msg("server failed")
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	log.Info().Msg("shutting down server...")

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		log.Fatal().Err(err).Msg("server forced to shutdown")
	}
	log.Info().Msg("server exited")
}
