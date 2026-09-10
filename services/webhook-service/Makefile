.PHONY: build test lint run

build: ## Build webhook service
	go build -o bin/server ./cmd/server

test: ## Run webhook service tests
	go test ./...

lint: ## Run webhook service linter
	golangci-lint run

run: ## Run webhook service
	go run ./cmd/server
