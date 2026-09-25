.PHONY: help infra-up infra-down up down build test test-coverage test-api-flows test-api-flows-collect lint deploy-dev teardown-dev seed wait-for-db security-scan test-report build-report testdata-validate testdata-clean testdata-setup-schema batch-usage-rollup batch-usage-rollup-seed seed-legacy seed-legacy-validate dev-backend dev-web dev-admin dev-android dev-electron dast-list dast-scan dast-verify dast-baseline dast-zap procs-validate procs-up procs-down procs-record procs-list procs-parity procs-rules-gate insurance-up insurance-down insurance-test legacy-etl-list legacy-etl-run legacy-etl-gen-data legacy-etl-gen-history legacy-sftp-up legacy-sftp-down oracle-billing-up oracle-billing-down oracle-billing-seed oracle-record oracle-parity tp-pain-mongodb tp-break-oracle-mongodb tp-smoke tp-usage-demo tp-month-end tp-run-branch demo-incident tp-pain-aws tp-pain-aws-break tp-pain-aws-restore tp-pain-aws-stop tp-preflight tp-preflight-databricks tp-preflight-atlas tp-preflight-aws tp-validate-schemas tp-validate-contracts tp-validate-recon tp-fixture-land tp-fixture-verify tp-fixture-clean dbx-showcase dbx-showcase-help tp-legacy-pain deps-inventory deps-gate deps-command deps-transcript deps-transcript-baseline deps-tests deps-record dast-coverage dast-routes dast-test eq-list eq-gate eq-baseline eq-verify eq-exploit eq-exploit-refactored eq-tests eq-record

SHELL := /bin/bash

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

tp-preflight: ## Check platform capabilities (PLATFORM=databricks|atlas|aws)
	@test "$(PLATFORM)" = databricks -o "$(PLATFORM)" = atlas -o "$(PLATFORM)" = aws || { echo "PLATFORM must be databricks, atlas, or aws" >&2; exit 2; }
	@case "$(PLATFORM)" in \
		databricks) $(MAKE) tp-preflight-databricks ;; \
		atlas) $(MAKE) tp-preflight-atlas ;; \
		aws) $(MAKE) tp-preflight-aws ;; \
	esac

tp-preflight-databricks: ## Check Databricks capability paths and emit a manifest
	scripts/tp-preflight-databricks.sh

tp-preflight-atlas: ## Check MongoDB Atlas capability paths and emit a manifest
	scripts/tp-preflight-atlas.sh

tp-preflight-aws: ## Check AWS capability paths and leftovers
	scripts/tp-preflight-aws.sh

tp-validate-schemas: ## Validate the contract/recon schemas themselves against their metaschema
	uv run --no-project --with check-jsonschema==0.38.0 check-jsonschema --check-metaschema docs/tech-partnerships/contracts/schema/*.schema.json

tp-validate-contracts: ## Validate JSON contracts (intentionally fails until prose contracts are migrated)
	uv run --no-project --with jsonschema==4.25.1 --with rfc3339-validator==0.1.4 python3 scripts/tp_validate.py contracts

tp-validate-recon: ## Validate recon reports (FILE=<path>; no reports is valid, other JSON is informational)
	uv run --no-project --with jsonschema==4.25.1 --with rfc3339-validator==0.1.4 python3 scripts/tp_validate.py recon $(FILE)

tp-fixture-land: ## Land source artifacts in the local Databricks transport fixture (NS=<ns>)
	python3 scripts/tp_databricks/local_fixture.py land --ns $${NS:-fixture} --source $${FIXTURE_SOURCE:-etl/legacy-extra}

tp-fixture-verify: ## Verify local fixture bytes and checksums (NS=<ns>)
	python3 scripts/tp_databricks/local_fixture.py verify --ns $${NS:-fixture}

tp-fixture-clean: ## Remove local Databricks transport fixture (NS=<ns>)
	python3 scripts/tp_databricks/local_fixture.py clean --ns $${NS:-fixture}

# Live Databricks billing-history showcase (needs DATABRICKS_DEMO_HOST/TOKEN).
# Serverless SQL only; every schedule it creates stays PAUSED.
dbx-showcase: ## Run a showcase step (CMD=<provision|land|expectations|backfill|recon|timetravel|lineage|dashboard|alert|pipeline|run-pipeline|recon-job|run-job|drift|status|demo-preflight|teardown> NS=<ns>)
	@test -n "$(CMD)" || { echo "usage: make dbx-showcase CMD=<step> [NS=<ns>] [ARGS=...]"; exit 2; }
	python3 scripts/tp_dbx/showcase.py --ns $${NS:-demo} $(CMD) $(ARGS)

dbx-showcase-help: ## List the Databricks billing-history showcase steps
	python3 scripts/tp_dbx/showcase.py --help

PROCS_COMPOSE = docker compose -f docker-compose.procs.yml -p otterworks-procs-$(NS)
PROCS_UV = uv run --with psycopg[binary]==3.2.9 --with pyyaml==6.0.2
PROCS_PORT_OFFSET = $(shell if command -v python3 >/dev/null 2>&1 && test -n "$(NS)"; then python3 -c "import zlib; print(zlib.crc32('$(NS)'.encode()) % 1000)"; fi)
PROCS_DB_PORT = $(shell test -n "$(PROCS_PORT_OFFSET)" && python3 -c "print(55432 + $(PROCS_PORT_OFFSET))")
PROCS_APP_PORT = $(shell test -n "$(PROCS_PORT_OFFSET)" && python3 -c "print(8096 + $(PROCS_PORT_OFFSET))")
PROCS_TARGET_DB_PORT = $(shell test -n "$(PROCS_PORT_OFFSET)" && python3 -c "print(56432 + $(PROCS_PORT_OFFSET))")
PROCS_TARGET_PORT = $(shell test -n "$(PROCS_PORT_OFFSET)" && python3 -c "print(12096 + $(PROCS_PORT_OFFSET))")
PROCS_ENV = NS=$(NS) PROCS_DB_PORT=$(PROCS_DB_PORT) PROCS_APP_PORT=$(PROCS_APP_PORT) PROCS_TARGET_DB_PORT=$(PROCS_TARGET_DB_PORT) PROCS_TARGET_PORT=$(PROCS_TARGET_PORT)

procs-validate:
	@test -n "$(NS)" || (echo "NS is required, e.g. make procs-up NS=dev" >&2; exit 2)
	@command -v python3 >/dev/null 2>&1 || (echo "python3 is required for namespace port derivation" >&2; exit 2)
	@test -n "$(PROCS_PORT_OFFSET)" || (echo "could not derive namespace port offset" >&2; exit 2)

procs-up: procs-validate ## Start the legacy billing stored-procedure stack (NS=<namespace>)
	$(PROCS_ENV) $(PROCS_COMPOSE) up -d --build --wait

procs-down: procs-validate ## Stop the legacy billing stored-procedure stack (NS=<namespace>)
	$(PROCS_ENV) $(PROCS_COMPOSE) down -v

procs-record: procs-validate ## Record legacy billing transcripts (NS=<namespace>, MODULE and OUTPUT_DIR optional)
	TZ=UTC LC_ALL=C $(PROCS_ENV) DB_NAME=billing_$(NS) DB_PORT=$(PROCS_DB_PORT) $(PROCS_UV) procs/harness/record.py $(if $(MODULE),--module $(MODULE),) $(if $(OUTPUT_DIR),--output-dir $(OUTPUT_DIR),) $(if $(ALLOW_RERECORD),--allow-rerecord,) $(if $(RERECORD_REASON),--rerecord-reason $(RERECORD_REASON),)

procs-list: ## List stored-procedure modules and scenarios
	$(PROCS_UV) procs/harness/list.py $(if $(MODULE),--module $(MODULE),)

procs-parity: procs-validate ## Replay extracted billing scenarios (NS=<namespace>, MODULE and SCENARIO optional)
	TZ=UTC LC_ALL=C $(PROCS_ENV) BILLING_SVC_URL=$${BILLING_SVC_URL:-http://localhost:$(PROCS_TARGET_PORT)} $(PROCS_UV) procs/harness/replay.py $(if $(MODULE),--module $(MODULE),) $(if $(SCENARIO),--scenario $(SCENARIO),)

procs-rules-gate: ## Validate the approved HITL rule ledger (MODULE=<module> or ALL=1)
	@test -n "$(MODULE)$(ALL)" || (echo "MODULE or ALL=1 is required" >&2; exit 2)
	uv run --with pyyaml==6.0.2 procs/harness/rules_gate.py $(if $(ALL),--all,--module $(MODULE))

# --- Industry Solutions: insurance Commission Pay (Oracle) ---

INSURANCE_COMPOSE = docker compose -f docker-compose.insurance.yml -p otterworks-insurance-$(NS)
INSURANCE_DB_PORT = $(shell test -n "$(PROCS_PORT_OFFSET)" && python3 -c "print(51521 + $(PROCS_PORT_OFFSET))")
INSURANCE_ENV = NS=$(NS) INSURANCE_DB_PORT=$(INSURANCE_DB_PORT)
INSURANCE_SQLPLUS = docker exec -i otterworks-insurance-$(NS)-insurance-oracle-1 sqlplus -s

insurance-up: procs-validate ## Start the Oracle insurance Commission Pay fixture (NS=<namespace>)
	$(INSURANCE_ENV) $(INSURANCE_COMPOSE) up -d --wait --wait-timeout 900

insurance-down: procs-validate ## Stop the Oracle insurance fixture and drop its data (NS=<namespace>)
	$(INSURANCE_ENV) $(INSURANCE_COMPOSE) down -v

insurance-test: procs-validate ## Run the Commission Pay OLTP + OLAP test suites (NS=<namespace>)
	$(INSURANCE_SQLPLUS) commission_pay/commission_pay@localhost:1521/FREEPDB1 @/opt/oracle/scripts/insurance/tests/run_tests.sql
	$(INSURANCE_SQLPLUS) commission_dw/commission_dw@localhost:1521/FREEPDB1 @/opt/oracle/scripts/insurance/tests/run_olap_tests.sql

# --- Legacy Billing: Oracle billing estate (before-state for modernization demos) ---

ORACLE_BILLING_COMPOSE = docker compose -f docker-compose.oracle-billing.yml -p otterworks-oracle-billing
ORACLE_BILLING_DB_PORT ?= 52521
ORACLE_BILLING_UV = uv run --with oracledb==2.5.1

oracle-billing-up: ## Start the Oracle billing estate fixture (localhost:$(ORACLE_BILLING_DB_PORT), PDB FREEPDB1, schema OW_BILLING)
	ORACLE_BILLING_DB_PORT=$(ORACLE_BILLING_DB_PORT) $(ORACLE_BILLING_COMPOSE) up -d --wait --wait-timeout 1200

oracle-billing-down: ## Stop the Oracle billing estate fixture and drop its data
	ORACLE_BILLING_DB_PORT=$(ORACLE_BILLING_DB_PORT) $(ORACLE_BILLING_COMPOSE) down -v

oracle-billing-seed: ## Seed the Oracle billing estate (NS=<namespace>, SCALE=demo|full; writes testdata/legacy/manifests/<NS>.json)
ifndef NS
	$(error NS is required, e.g. make oracle-billing-seed NS=dev)
endif
	$(call validate_ns)
	DB_PORT=$(ORACLE_BILLING_DB_PORT) $(ORACLE_BILLING_UV) testdata/legacy/oracle_billing_seed.py --ns $(NS) --scale $(or $(SCALE),demo)

TP_COMPOSE = docker compose -f docker-compose.yml -f docker-compose.tp.yml
TP_SERVICES = $(if $(filter core,$(PROFILE)),api-gateway auth-service document-service file-service web-app admin-dashboard legacy-billing usage-bridge,)

define tp_oracle_namespace_present
DB_PORT=$(ORACLE_BILLING_DB_PORT) $(ORACLE_BILLING_UV) python3 -c 'import os,oracledb; c=oracledb.connect(user=os.getenv("DB_USER","ow_billing"), password=os.getenv("DB_PASSWORD","ow_billing"), host=os.getenv("DB_HOST","localhost"), port=int(os.getenv("DB_PORT","52521")), service_name=os.getenv("DB_SERVICE","FREEPDB1")); x=c.cursor(); x.execute("select count(*) from invoice_header where batch_no = :1", [int.from_bytes(__import__("hashlib").sha256("$(NS)".encode()).digest()[:4], "big") % 90000000 + 1000000]); print("present" if x.fetchone()[0] else "missing"); c.close()'
endef

tp-up: ## Start the opt-in tech-partnerships wired estate (NS=<namespace>, PROFILE=core optional)
ifndef NS
	$(error NS is required, e.g. make tp-up NS=dev)
endif
	$(call validate_ns)
	$(MAKE) oracle-billing-up
	@if test -f testdata/legacy/manifests/$(NS).json && { $(call tp_oracle_namespace_present); } | grep -qx present; then :; else $(MAKE) oracle-billing-seed NS=$(NS); fi
	$(MAKE) infra-up
	$(TP_COMPOSE) up -d --build --wait $(TP_SERVICES)
	@echo "Web: http://localhost:3000"
	@echo "Admin: http://localhost:4200"
	@echo "Legacy billing: http://localhost:8096"
	@echo "Oracle: localhost:$(ORACLE_BILLING_DB_PORT)"

tp-down: ## Stop the opt-in tech-partnerships wired estate (does not tear down Oracle)
	$(TP_COMPOSE) down

tp-seed: ## Seed the Oracle, companion, and legacy ETL estates (NS=<namespace>)
ifndef NS
	$(error NS is required, e.g. make tp-seed NS=dev)
endif
	$(call validate_ns)
	$(MAKE) oracle-billing-seed NS=$(NS)
	$(MAKE) seed-legacy NS=$(NS)
	$(MAKE) legacy-etl-gen-data NS=$(NS)

tp-usage-demo: ## Create a document and verify asynchronous billing usage (NS=<namespace>)
ifndef NS
	$(error NS is required, e.g. make tp-usage-demo NS=demo)
endif
	$(call validate_ns)
	scripts/tp/usage_demo.sh $(NS)

ORACLE_PARITY_UV = uv run --with oracledb==2.5.1 --with pyyaml==6.0.2
ORACLE_PARITY_RUN = procs/reports/oracle-parity-run

oracle-record: ## Record immutable Oracle billing transcripts (requires oracle-billing-up; MODULE optional)
	TZ=UTC LC_ALL=C DB_PORT=$(ORACLE_BILLING_DB_PORT) $(ORACLE_PARITY_UV) procs/harness/oracle_record.py $(if $(MODULE),--module $(MODULE),) $(if $(ALLOW_RERECORD),--allow-rerecord,)

oracle-parity: procs-validate ## Oracle vs Postgres parity run (NS=<namespace>; requires procs-up and oracle-billing-up)
	$(call validate_ns)
	DB_PORT=$(ORACLE_BILLING_DB_PORT) $(ORACLE_BILLING_UV) testdata/legacy/oracle_billing_seed.py --ns $(NS) --scale $(or $(SCALE),demo)
	rm -rf $(ORACLE_PARITY_RUN)/$(NS)
	TZ=UTC LC_ALL=C $(PROCS_ENV) DB_NAME=billing_$(NS) DB_PORT=$(PROCS_DB_PORT) $(PROCS_UV) procs/harness/record.py --output-dir $(ORACLE_PARITY_RUN)/$(NS)/postgres
	TZ=UTC LC_ALL=C DB_PORT=$(ORACLE_BILLING_DB_PORT) $(ORACLE_PARITY_UV) procs/harness/oracle_record.py --output-dir $(ORACLE_PARITY_RUN)/$(NS)/oracle
	TZ=UTC LC_ALL=C uv run procs/harness/oracle_parity.py --postgres-dir $(ORACLE_PARITY_RUN)/$(NS)/postgres --oracle-dir $(ORACLE_PARITY_RUN)/$(NS)/oracle --namespace $(NS)

# --- Local Development ---

infra-up: ## Start local infrastructure (Postgres, Redis, LocalStack, MeiliSearch)
	docker compose -f docker-compose.infra.yml up -d

infra-down: ## Stop local infrastructure
	docker compose -f docker-compose.infra.yml down

up: ## Start all services (add seed=1 to seed after start)
	docker compose -f docker-compose.infra.yml -f docker-compose.yml up -d --build
 ifdef seed
	@$(MAKE) --no-print-directory wait-for-db seed
 endif

down: ## Stop all application services
	docker compose -f docker-compose.infra.yml -f docker-compose.yml down

build: ## Build all service images
	docker compose -f docker-compose.infra.yml -f docker-compose.yml build

seed: ## Seed development data (services must be running)
	DB_PORT=$${DB_PORT:-$${POSTGRES_HOST_PORT:-5432}} uv run scripts/seed.py

wait-for-db: ## Wait for Postgres to accept connections
	@echo "Waiting for Postgres to be healthy..."
	@for i in $$(seq 1 30); do \
		docker exec otterworks-postgres pg_isready -q 2>/dev/null && exit 0; \
		sleep 1; \
	done; echo "Timed out waiting for Postgres" && exit 1

logs: ## Tail logs for all services
	docker compose -f docker-compose.infra.yml -f docker-compose.yml logs -f

# --- App Dev Targets ---
# One-command startup for each frontend app, running from source against the
# Dockerized backend. The compose web-app/admin-dashboard containers are stopped
# where they would clash with the dev servers on ports 3000/4200.

COMPOSE := docker compose -f docker-compose.infra.yml -f docker-compose.yml
# Collab websocket as exposed by docker-compose (host port 8084); source builds
# otherwise default to :8085, which only matches the k8s dev environment.
COLLAB_WS_URL := ws://localhost:8084

dev-backend: ## Start the Dockerized backend (all services except the frontend containers)
	$(COMPOSE) up -d $$($(COMPOSE) config --services | grep -vE '^(web-app|admin-dashboard)$$')
	@echo "Backend up - API gateway on http://localhost:8080 (fresh DB? run: make seed)"

dev-web: dev-backend ## Start the client-app web dev server (HMR) on :3000
	@$(COMPOSE) stop web-app 2>/dev/null || true
	cd frontend/client-app && { [ -d node_modules ] || npm ci; } && \
		VITE_COLLAB_WS_URL=$(COLLAB_WS_URL) npm run dev

dev-admin: dev-backend ## Start the admin dashboard dev server (HMR) on :4200
	@$(COMPOSE) stop admin-dashboard 2>/dev/null || true
	cd frontend/admin-dashboard && { [ -d node_modules ] || npm ci; } && npm start

dev-android: dev-backend ## Build the web bundle and run the Android app on an emulator/device
	cd frontend/client-app && { [ -d node_modules ] || npm ci; } && \
		VITE_COLLAB_WS_URL=ws://10.0.2.2:8084 npm run build && \
		npx cap sync android && npx cap run android

dev-electron: dev-backend ## Build the web bundle and launch the Electron desktop app
	cd frontend/client-app && { [ -d node_modules ] || npm ci; } && \
		VITE_COLLAB_WS_URL=$(COLLAB_WS_URL) npm run build
	cd frontend/client-app/desktop && { [ -d node_modules ] || npm ci; } && npm start

# --- Per-Service Builds ---

build-gateway: ## Build API Gateway
	cd services/api-gateway && go build -o bin/server ./cmd/server

build-auth: ## Build Auth Service
	cd services/auth-service && ./gradlew bootJar

build-file: ## Build File Service
	cd services/file-service && cargo build --release

build-document: ## Build Document Service
	cd services/document-service && pip install -e .

build-collab: ## Build Collaboration Service
	cd services/collab-service && npm run build

build-notification: ## Build Notification Service
	cd services/notification-service && ./gradlew build

build-search: ## Build Search Service
	cd services/search-service && pip install -e .

build-analytics: ## Build Analytics Service
	cd services/analytics-service && sbt compile

build-admin: ## Build Admin Service
	cd services/admin-service && bundle install

build-audit: ## Build Audit Service
	cd services/audit-service && dotnet build

build-web: ## Build Web Frontend
	cd frontend/web-app && npm run build

build-admin-dash: ## Build Admin Dashboard
	cd frontend/admin-dashboard && npm run build

# --- Testing ---

test: ## Run tests for all services
	@echo "=== API Gateway (Go) ===" && cd services/api-gateway && go test ./...
	@echo "=== Auth Service (Java) ===" && cd services/auth-service && ./gradlew test
	@echo "=== File Service (Rust) ===" && cd services/file-service && cargo test
	@echo "=== Document Service (Python) ===" && cd services/document-service && pytest
	@echo "=== Collab Service (Node.js) ===" && cd services/collab-service && npm test
	@echo "=== Notification Service (Kotlin) ===" && cd services/notification-service && ./gradlew test
	@echo "=== Search Service (Python) ===" && cd services/search-service && pytest
	@echo "=== Analytics Service (Scala) ===" && cd services/analytics-service && sbt test
	@echo "=== Admin Service (Ruby) ===" && cd services/admin-service && bundle exec rspec
	@echo "=== Audit Service (C#) ===" && cd services/audit-service && dotnet test
	@echo "=== Web Frontend ===" && cd frontend/web-app && npm test
	@echo "=== Admin Dashboard ===" && cd frontend/admin-dashboard && npm test

test-coverage: ## Run tests with coverage for all services
	@echo "=== Document Service ===" && cd services/document-service && pytest --cov=app --cov-report=term-missing || true
	@echo "=== Search Service ===" && cd services/search-service && pytest --cov=app --cov-report=term-missing || true
	@echo "=== Collab Service ===" && cd services/collab-service && npm test -- --coverage || true
	@echo "=== API Gateway ===" && cd services/api-gateway && go test -cover ./... || true
	@echo "=== Admin Service ===" && cd services/admin-service && bundle exec rspec --format documentation || true
	@echo "=== Auth Service ===" && cd services/auth-service && ./gradlew test jacocoTestReport || true
	@echo "=== File Service ===" && cd services/file-service && cargo test 2>&1 | tail -5 || true

tp-smoke: ## Golden-path smoke gate for tech-partnerships (mirrors .github/workflows/tp-golden-smoke.yml)
	@echo "=== Estate Make targets parse (dry-run) ==="
	@$(MAKE) -n oracle-billing-up > /dev/null
	@$(MAKE) -n seed-legacy NS=ci > /dev/null
	@$(MAKE) -n legacy-etl-list > /dev/null
	@$(MAKE) -n procs-parity NS=ci > /dev/null
	@$(MAKE) -n tp-up NS=ci > /dev/null
	@echo "=== Oracle billing compose config lint ==="
	docker compose -f docker-compose.oracle-billing.yml config > /dev/null
	docker compose -f docker-compose.yml -f docker-compose.tp.yml config > /dev/null
	@echo "=== Golden 'make -n test' still parses ==="
	@$(MAKE) -n test > /dev/null
	@echo "=== TP portal visual renderers (stdlib-only, sample inputs) ==="
	python3 scripts/tp_portal/render_scorecard.py scripts/tp_portal/samples/sample-parity.recon.json --out /tmp/tp-smoke-scorecard.html > /dev/null
	python3 scripts/tp_portal/render_load_charts.py --before scripts/tp_portal/samples/sample-load-monolith.json --after scripts/tp_portal/samples/sample-load-aws.json --out /tmp/tp-smoke-loadcharts.html > /dev/null
	@echo "=== TP portal demo harness self-tests (offline, nothing started) ==="
	scripts/tp_portal/pain_portal.sh selftest > /dev/null
	scripts/tp_portal/demo_incident_generic.sh self-test > /dev/null
	@echo "=== API Gateway (Go) ==="
	cd services/api-gateway && go vet ./... && go test ./... && go build -o /dev/null ./cmd/server
	@echo "=== Collab Service (Node.js) ==="
	cd services/collab-service && { [ -d node_modules ] || npm ci; } && npm run lint && npm test && npm run build
	@echo "=== Client App (Node.js) ==="
	cd frontend/client-app && { [ -d node_modules ] || npm ci; } && npm run lint && npm test -- --run && npm run build
	@echo "=== Search Service (Python) ==="
	cd services/search-service && uv run --no-project --with-requirements requirements-dev.txt python -m pytest
	@echo "=== Legacy Billing (Python) ==="
	cd services/legacy-billing && uv run --with pytest --with boto3==1.40.35 --with requests==2.32.5 --with flask==3.1.1 --with oracledb==2.5.1 --with 'psycopg[binary]==3.2.9' python -m pytest -q && uv run --with pytest --with boto3==1.40.35 --with requests==2.32.5 python -m pytest -q bridge/tests
	cd etl/legacy-extra/tools && uv run --with pytest --with flask==3.1.1 --with oracledb==2.5.1 python -m pytest -q
	@echo "tp-smoke: all checks passed"

tp-run-branch: ## Cut and push the per-run working branch for a rehearsal (TRACK=mongodb|databricks|aws|modernize)
	@scripts/tp-run-branch.sh $(TRACK)

AIRBYTE_TF = terraform -chdir=ingestion/airbyte
AIRBYTE_LANDING_DIR ?= $(HOME)/airbyte-landing

tp-airbyte-init: ## Init the Airbyte Terraform module against the per-namespace state key (NS=<ns>)
ifndef NS
	$(error NS is required, e.g. make tp-airbyte-init NS=demo)
endif
	$(call validate_ns)
	$(AIRBYTE_TF) init -input=false -backend-config="key=ow-tp/airbyte/$(NS).tfstate"

tp-airbyte-plan: ## Plan the Airbyte pipeline (NS=<ns>; needs AIRBYTE_*/DATABRICKS_DEMO_*/AWS_* in env)
ifndef NS
	$(error NS is required, e.g. make tp-airbyte-plan NS=demo)
endif
	$(call validate_ns)
	TF_VAR_namespace=$(NS) $(AIRBYTE_TF) plan -input=false

tp-airbyte-apply: ## Apply the Airbyte pipeline (NS=<ns>)
ifndef NS
	$(error NS is required, e.g. make tp-airbyte-apply NS=demo)
endif
	$(call validate_ns)
	TF_VAR_namespace=$(NS) $(AIRBYTE_TF) apply -input=false -auto-approve

tp-airbyte-land: ## Export the Oracle billing tables for NS and upload them to the landing bucket (NS=<ns>)
ifndef NS
	$(error NS is required, e.g. make tp-airbyte-land NS=demo)
endif
	$(call validate_ns)
	ORACLE_PORT=$(ORACLE_BILLING_DB_PORT) uv run --with boto3==1.40.35 --with oracledb==2.5.1 python ingestion/airbyte/tools/export_billing_csv.py --ns $(NS) --out $(AIRBYTE_LANDING_DIR) --bucket $$($(AIRBYTE_TF) output -raw landing_bucket)

tp-airbyte-sync: ## Run the connection twice and write the recon report (NS=<ns>)
ifndef NS
	$(error NS is required, e.g. make tp-airbyte-sync NS=demo)
endif
	$(call validate_ns)
	AIRBYTE_CONNECTION_ID=$$($(AIRBYTE_TF) output -raw connection_id) python3 ingestion/airbyte/tools/sync_and_recon.py --ns $(NS) --manifest $(AIRBYTE_LANDING_DIR)/$(NS)/manifest.json

tp-airbyte-diagnose: ## Print the last non-green job on the billing connection and what the API exposes about it (NS=<ns>)
ifndef NS
	$(error NS is required, e.g. make tp-airbyte-diagnose NS=demo)
endif
	$(call validate_ns)
	AIRBYTE_CONNECTION_ID=$$($(AIRBYTE_TF) output -raw connection_id) python3 ingestion/airbyte/tools/diagnose.py

tp-airbyte-repair: ## Re-import the billing S3 source so Terraform re-pushes its credentials, then apply only the billing targets (NS=<ns>)
ifndef NS
	$(error NS is required, e.g. make tp-airbyte-repair NS=demo)
endif
	$(call validate_ns)
	set -e; \
	SCHEMA=$$($(AIRBYTE_TF) output -raw destination_schema); \
	case "$$SCHEMA" in *.airbyte_$(NS)) ;; *) echo "initialised state is for '$$SCHEMA', not NS=$(NS); run make tp-airbyte-init NS=$(NS) first" >&2; exit 1;; esac; \
	SOURCE_ID=$$($(AIRBYTE_TF) output -raw source_id); \
	BACKUP=$$(mktemp -t airbyte-$(NS)-XXXXXX); trap 'rm -f $$BACKUP' EXIT; \
	$(AIRBYTE_TF) state pull > $$BACKUP; \
	TF_VAR_namespace=$(NS) $(AIRBYTE_TF) state rm airbyte_source_s3.billing_landing; \
	if ! TF_VAR_namespace=$(NS) $(AIRBYTE_TF) import -input=false airbyte_source_s3.billing_landing $$SOURCE_ID; then \
	  echo "import failed; restoring previous state" >&2; $(AIRBYTE_TF) state push -force $$BACKUP; exit 1; \
	fi; \
	TF_VAR_namespace=$(NS) $(AIRBYTE_TF) apply -input=false -auto-approve -target=airbyte_source_s3.billing_landing -target=airbyte_connection.billing

tp-pain-mongodb: ## Beat 1 opener: "just add a field" blast radius on the Oracle estate (NS=<namespace>; needs oracle-billing-up + oracle-billing-seed)
ifndef NS
	$(error NS is required, e.g. make tp-pain-mongodb NS=demo)
endif
	$(call validate_ns)
	DB_PORT=$(ORACLE_BILLING_DB_PORT) scripts/tp-pain-mongodb.sh --ns $(NS)

tp-break-oracle-mongodb: ## Beat 4 switch: legacy-shaped poison docs vs $$jsonSchema (NS=<ns>; UNDO=1 undo, DRY_RUN=1 preview, SELF_TEST=1 local fixture test)
ifdef SELF_TEST
	scripts/tp-break-oracle-mongodb.sh --self-test
else ifndef NS
	$(error NS is required, e.g. make tp-break-oracle-mongodb NS=demo)
else
	$(call validate_ns)
	scripts/tp-break-oracle-mongodb.sh --ns $(NS) $(if $(UNDO),--undo,) $(if $(DRY_RUN),--dry-run,)
endif

demo-incident: ## Stage the one live demo beat: a bad deploy that trips the alarm->Devin loop (NS=<ns>; script is authored per run)
	@test -n "$(NS)" || { echo "demo-incident: set NS=<namespace> (e.g. NS=demo)"; exit 1; }
	@test -x scripts/tp_portal/demo_incident.sh || { echo "demo-incident: scripts/tp_portal/demo_incident.sh not found or not executable."; echo "It is authored by each tp-run/aws-* run (it needs that run's function names and API URL)."; echo "See docs/tech-partnerships/runbook-aws-portal-demo-day.md."; exit 1; }
	scripts/tp_portal/demo_incident.sh $(NS)

tp-pain-aws: ## Beat 1 opener: start the legacy portal locally, seeded, with a green capability strip
	scripts/tp_portal/pain_portal.sh start

tp-pain-aws-break: ## Beat 1 break: fail ONE capability (feedback) and watch every capability die with the process
	scripts/tp_portal/pain_portal.sh break

tp-pain-aws-restore: ## Beat 1 undo: clean restart of the legacy portal, green strip again
	scripts/tp_portal/pain_portal.sh restore

tp-pain-aws-stop: ## Beat 1 cleanup: stop the legacy portal started by tp-pain-aws
	scripts/tp_portal/pain_portal.sh stop

test-api-flows: ## Run black-box API flow tests against the local API gateway
	UV_PROJECT_ENVIRONMENT=.venv uv run python -m pytest tests/api

test-api-flows-collect: ## Collect black-box API flow tests without running them
	UV_PROJECT_ENVIRONMENT=.venv uv run python -m pytest tests/api --collect-only -q

lint: ## Lint all services
	@echo "=== API Gateway ===" && cd services/api-gateway && golangci-lint run
	@echo "=== Auth Service ===" && cd services/auth-service && ./gradlew spotlessCheck
	@echo "=== File Service ===" && cd services/file-service && cargo clippy -- -D warnings
	@echo "=== Document Service ===" && cd services/document-service && ruff check .
	@echo "=== Collab Service ===" && cd services/collab-service && npm run lint
	@echo "=== Search Service ===" && cd services/search-service && ruff check .
	@echo "=== Web Frontend ===" && cd frontend/web-app && npm run lint
	@echo "=== Admin Dashboard ===" && cd frontend/admin-dashboard && npm run lint

# --- Synthetic Test Data ---

# Guard: NS must be alphanumeric/underscore only (prevents SQL injection)
define validate_ns
$(if $(filter ok,$(shell echo '$(NS)' | grep -qE '^[A-Za-z0-9_]+$$' && echo ok)),,$(error NS must contain only letters, digits, and underscores))
endef

testdata-validate: ## Validate generated test data (NS=<namespace>, CRITERIA=<file>)
ifndef NS
	$(error NS is required, e.g. make testdata-validate NS=dev)
endif
	$(call validate_ns)
	uv run testdata/harness/validate.py --ns $(NS) $(if $(CRITERIA),--criteria $(CRITERIA),)

testdata-clean: ## Drop a test-data namespace schema (NS=<namespace>)
ifndef NS
	$(error NS is required, e.g. make testdata-clean NS=dev)
endif
	$(call validate_ns)
	@echo "Dropping schema otterworks_$(NS)..."
	PGPASSWORD=$${DB_PASSWORD:-otterworks_dev} psql \
		-h $${DB_HOST:-localhost} -p $${DB_PORT:-$${POSTGRES_HOST_PORT:-5432}} \
		-U $${DB_USER:-otterworks} -d $${DB_NAME:-otterworks} \
		-c "DROP SCHEMA IF EXISTS otterworks_$(NS) CASCADE;"
	@echo "Done."

testdata-setup-schema: ## Create a namespaced schema (NS=<namespace>)
ifndef NS
	$(error NS is required, e.g. make testdata-setup-schema NS=dev)
endif
	$(call validate_ns)
	@echo "Creating schema otterworks_$(NS)..."
	PGPASSWORD=$${DB_PASSWORD:-otterworks_dev} psql \
		-h $${DB_HOST:-localhost} -p $${DB_PORT:-5432} \
		-U $${DB_USER:-otterworks} -d $${DB_NAME:-otterworks} \
		-f testdata/harness/create_schema.sql \
		-v ns=$(NS)
	@echo "Done."

# --- Legacy Seed Data (tech-partnerships demo estates) ---

comma := ,
SEED_LEGACY_SCALE = $(if $(SCALE),$(SCALE),demo)
SEED_LEGACY_TARGETS = $(if $(TARGETS),$(TARGETS),postgres$(comma)dynamodb$(comma)s3)

seed-legacy: ## Seed legacy demo data (NS=<ns>, SCALE=demo|full, TARGETS=postgres,dynamodb,s3)
ifndef NS
	$(error NS is required, e.g. make seed-legacy NS=dev)
endif
	$(call validate_ns)
	uv run testdata/legacy/seed.py --ns $(NS) --scale $(SEED_LEGACY_SCALE) --targets "$(SEED_LEGACY_TARGETS)"

seed-legacy-validate: ## Re-derive counts/checksums from the stores and assert they match the manifest (NS=<ns>, TARGETS=...)
ifndef NS
	$(error NS is required, e.g. make seed-legacy-validate NS=dev)
endif
	$(call validate_ns)
	uv run testdata/legacy/validate.py --ns $(NS) --targets "$(SEED_LEGACY_TARGETS)"

# --- Infrastructure ---

tf-init: ## Initialize Terraform
	cd infrastructure/terraform && terraform init

tf-plan: ## Plan Terraform changes
	cd infrastructure/terraform && terraform plan -var-file=environments/dev.tfvars

tf-apply: ## Apply Terraform changes
	cd infrastructure/terraform && terraform apply -var-file=environments/dev.tfvars -auto-approve

tf-destroy: ## Destroy Terraform resources
	cd infrastructure/terraform && terraform destroy -var-file=environments/dev.tfvars -auto-approve

deploy-dev: ## Deploy all services to dev EKS
	./scripts/deploy-dev.sh

teardown-dev: ## Tear down dev environment
	./scripts/teardown-dev.sh

# --- Security ---

security-scan: ## Run security scans across all services
	@echo "=== Trivy Filesystem Scan ==="
	trivy fs --config security/scanning/trivy-config.yaml . || true
	@echo ""
	@echo "=== Node.js Audit (collab-service) ==="
	cd services/collab-service && npm audit 2>/dev/null || true
	@echo ""
	@echo "=== Python Audit (search-service) ==="
	cd services/search-service && pip-audit -r requirements.txt 2>/dev/null || true
	@echo ""
	@echo "=== Ruby Audit (admin-service) ==="
	cd services/admin-service && bundle-audit check 2>/dev/null || true
	@echo ""
	@echo "=== Report Service (skipped - legacy) ==="

# --- Dynamic Application Security Testing (DAST) ---
#
# DAST attacks the *running* application through the API gateway. TARGET can be
# the local stack (default), a tenant URL, or a preview environment.

DAST_TARGET ?= http://localhost:8080
# Each script declares its own dependencies (PEP 723), so `uv run` needs no --with.
# Note that make reports 2 for any failed recipe: to act on the harness's own exit
# codes (1 findings, 2 nothing tested, 3 no verdict), call security/dast/run.sh.
DAST := uv run security/dast/harness/dast_scan.py
DAST_COVERAGE := uv run security/dast/harness/dast_coverage.py

dast-list: ## List the registered DAST attack probes
	$(DAST) --list

dast-scan: ## Run the DAST suite against a running app (DAST_TARGET=<url>), gated by the baseline
	$(DAST) --target $(DAST_TARGET) $(if $(FAIL_ON),--fail-on $(FAIL_ON),)

dast-verify: ## Prove one finding is remediated (FINDING=<id> DAST_TARGET=<url>); baseline is ignored
ifndef FINDING
	$(error FINDING is required, e.g. make dast-verify FINDING=DAST-MISSING-SECURITY-HEADERS)
endif
	$(DAST) --target $(DAST_TARGET) --only $(FINDING) --no-baseline --fail-on info

dast-routes: ## List the edge-reachable routes read from the services' source
	uv run security/dast/harness/route_inventory.py

dast-coverage: ## Fail if a route the gateway proxies was never attacked by the last scan
	$(DAST_COVERAGE)

dast-test: ## Unit-test the harness itself (route extraction, coverage gate, perimeter verdicts)
	uv run --python '>=3.11' --with pytest --with httpx --with pyyaml --with tabulate \
		python -m pytest security/dast/harness/tests -q

dast-baseline: ## Record current findings as accepted (REASON="...")
	$(DAST) --target $(DAST_TARGET) --reason "$${REASON:-recorded by make dast-baseline}" --update-baseline

dast-zap: ## Run the OWASP ZAP baseline sweep and merge it into the DAST report
	@mkdir -p security/dast/reports
# ZAP writes its report *and* its generated automation plan into its working
# directory, and the image runs as uid 1000 while a CI runner is 1001 (running the
# container as the host uid instead is not an option: ZAP needs /home/zap, which
# only exists for uid 1000). Rather than open up a host directory, the working
# directory is a throwaway docker volume chowned to the image's uid from inside a
# container, so nothing on the host is ever writable by another local user. The
# rule file goes in read-only, and the report is read back out through the volume.
# The stale report is removed first, so "a report exists" can only mean this run
# produced one.
	@rm -f security/dast/reports/zap-report.json
	@set -e; \
	vol="dast-zap-$$$$"; \
	trap 'docker volume rm -f "$$vol" >/dev/null 2>&1' EXIT INT TERM; \
	docker volume create "$$vol" >/dev/null; \
	docker run --rm --user 0 -v "$$vol:/zap/wrk" \
		ghcr.io/zaproxy/zaproxy:stable chown 1000:1000 /zap/wrk; \
	docker run --rm --network host \
		-v "$$vol:/zap/wrk" \
		-v "$(CURDIR)/security/dast/zap/zap-baseline.conf:/zap/wrk/zap-baseline.conf:ro" \
		ghcr.io/zaproxy/zaproxy:stable zap-baseline.py \
		-t $(DAST_TARGET) -c zap-baseline.conf -J zap-report.json -I || true; \
	docker run --rm --user 0 -v "$$vol:/zap/wrk" ghcr.io/zaproxy/zaproxy:stable \
		sh -c 'cat /zap/wrk/zap-report.json 2>/dev/null' \
		> security/dast/reports/zap-report.json || true; \
	[ -s security/dast/reports/zap-report.json ] || rm -f security/dast/reports/zap-report.json
# A ZAP failure must not cost the probe suite: the sweep still reports, without it.
	@if [ -f security/dast/reports/zap-report.json ]; then \
		$(DAST) --target $(DAST_TARGET) --zap-report security/dast/reports/zap-report.json; \
	else \
		echo "::warning::ZAP produced no report (see the log above); the passive sweep is"\
		     "missing from this run. Running the probe suite on its own."; \
		$(DAST) --target $(DAST_TARGET); \
	fi

# --- Dependency CVE remediation ---
#
# The advisory (security/deps/advisory.yaml) names the artifact and its vulnerable
# range; modules.yaml registers every JVM module so the blast radius cannot be
# partial. Reports land in security/deps/reports/ (git-ignored: collect them as CI
# artifacts and paste the summary into the PR).

DEPS := uv run --with pyyaml==6.0.2 --with tabulate==0.10.0 security/deps/harness/deps_check.py

deps-inventory: ## Report the blast radius of the advisory across every JVM module
	$(DEPS) inventory

deps-gate: ## Fail if the vulnerable version is still reachable from any dependency tree
	$(DEPS) gate

deps-command: ## Print the harness invocation, for callers that need its exact exit code
	@echo '$(DEPS)'

deps-tests: ## Build and run every affected module's own suite (MODULE=<id> optional)
	$(DEPS) tests $(if $(MODULE),--module $(MODULE),)

deps-transcript: ## Grade interpolation behavior after remediation (MODULE=<id> optional)
	$(DEPS) transcript --stage remediated $(if $(MODULE),--module $(MODULE),)

deps-transcript-baseline: ## Prove the recorded before-state still reproduces (MODULE=<id> optional)
	$(DEPS) transcript --stage baseline $(if $(MODULE),--module $(MODULE),)

deps-record: ## Record the transcripts as the reference evidence (REASON="..." required)
	@test -n "$(REASON)" || (echo 'REASON is required, e.g. make deps-record REASON="baseline on commons-text 1.9"' >&2; exit 2)
	$(DEPS) transcript --record --reason "$(REASON)" $(if $(MODULE),--module $(MODULE),) $(if $(ALLOW_RERECORD),--allow-rerecord,)

test-report: ## Run report-service tests only
	cd services/report-service && mvn test

build-report: ## Build report-service
	cd services/report-service && mvn package -DskipTests

# --- Batch jobs (legacy scheduled processing) ---

batch-usage-rollup: ## Run the nightly usage-rollup batch job locally (OUT=<path> optional)
	ROLLUP_OUTPUT=$${OUT:-rollup-output.json} scripts/run-usage-rollup.sh

batch-usage-rollup-seed: ## Regenerate the deterministic usage-rollup seed events
	cd services/analytics-service && python3 scripts/generate_seed_events.py

# --- Legacy polyglot batch estate (etl/legacy-extra/, tech-partnerships demo) ---

legacy-etl-list: ## List the legacy polyglot batch jobs (etl/legacy-extra/)
	@echo "Legacy batch jobs (run with: make legacy-etl-run JOB=<name>):"
	@echo "  sftp_ingest_poll          ksh   poll SFTP drop dir, stage CUSTBILL files"
	@echo "  parse_custbill_fixedwidth bash  sed/awk/cut fixed-width parser -> .psv"
	@echo "  finance_excel_report      perl  CSV-renamed-to-.xls finance report + stub sendmail"
	@echo "  run_all                   bash  full chain, sleep-based 'dependency management'"
	@echo "Sample input: make legacy-etl-gen-data [NS=dev]"
	@echo "Multi-year history: make legacy-etl-gen-history [NS=dev] [START_YEAR=2019] [END_YEAR=2024]"

# Deterministic-run wrapper: pins TZ/LC_ALL (and, with TP_FAKETIME set, the
# clock) so golden recordings and byte-identical parity claims are stable
# across machines and reruns.
TP_DET := scripts/tp-run-deterministic.sh

legacy-etl-gen-data: ## Generate deterministic CUSTBILL sample input (NS=<ns>)
	$(TP_DET) perl etl/legacy-extra/tools/gen_sample_data.pl $${NS:-dev}

legacy-etl-gen-history: ## Generate multi-year dated CUSTBILL history (NS=<ns> START_YEAR= END_YEAR= ROWS_PER_MONTH=)
	$(TP_DET) perl etl/legacy-extra/tools/gen_history_data.pl $${NS:-dev} $${START_YEAR:-2019} $${END_YEAR:-2024} $${ROWS_PER_MONTH:-40}

legacy-etl-run: ## Run one legacy batch job (JOB=<name>, see legacy-etl-list)
	@test -n "$(JOB)" || { echo "usage: make legacy-etl-run JOB=<name>"; exit 1; }
	@case "$(JOB)" in \
	  sftp_ingest_poll)           command -v ksh >/dev/null || { echo "ksh required (sudo apt-get install -y ksh)"; exit 1; }; $(TP_DET) etl/legacy-extra/jobs/sftp_ingest_poll.ksh ;; \
	  parse_custbill_fixedwidth)  $(TP_DET) etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh ;; \
	  finance_excel_report)       $(TP_DET) perl etl/legacy-extra/jobs/finance_excel_report.pl ;; \
	  run_all)                    command -v ksh >/dev/null || { echo "ksh required (sudo apt-get install -y ksh)"; exit 1; }; RUN_ALL_SLEEP=$${RUN_ALL_SLEEP:-0} $(TP_DET) etl/legacy-extra/run_all.sh ;; \
	  *) echo "unknown JOB '$(JOB)' (see: make legacy-etl-list)"; exit 1 ;; \
	esac

tp-month-end: ## Extract Oracle invoices and run the CUSTBILL month-end batch (NS=<ns>)
ifndef NS
	$(error NS is required, e.g. make tp-month-end NS=demo)
endif
	$(call validate_ns)
	@set -e; \
	base="$${OTTERWORKS_LEGACY_ROOT:-/tmp/otterworks-legacy}"; \
	root="$$base/$(NS)"; \
	mkdir -p "$$root/incoming" "$$root/reports"; \
	ORACLE_PORT=$(ORACLE_BILLING_DB_PORT) $(ORACLE_BILLING_UV) etl/legacy-extra/tools/oracle_custbill_extract.py --ns "$(NS)" --out "$$root/incoming"; \
	OTTERWORKS_LEGACY_ROOT="$$root" $(MAKE) legacy-etl-run JOB=parse_custbill_fixedwidth; \
	OTTERWORKS_LEGACY_ROOT="$$root" $(MAKE) legacy-etl-run JOB=finance_excel_report; \
	report=$$(ls -1t "$$root"/reports/finance_billing_*.csv | head -1); \
	published="$(CURDIR)/etl/legacy-extra/reports/$(NS)"; \
	mkdir -p "$$published"; \
	cp "$$report" "$$published/"; \
	cp "$${report%.csv}.xls" "$$published/"; \
	echo "finance report: $$report"; \
	echo "finance rows: $$(($$(wc -l < "$$report") - 1))"

tp-legacy-pain: ## Legacy-pain opener: blast radius + baseline + silent corruption (ACT=blast|baseline|poison|all|clean)
	@command -v ksh >/dev/null || { echo "ksh required (sudo apt-get install -y ksh)"; exit 1; }
	$(TP_DET) scripts/tp_dbx/legacy_pain.sh $${ACT:-all}

legacy-sftp-up: ## Start the optional localhost-only SFTP drop fixture
	mkdir -p $${OTTERWORKS_LEGACY_ROOT:-/tmp/otterworks-legacy}/sftp-drop/upload
	LEGACY_SFTP_UID=$$(id -u) docker compose -f etl/legacy-extra/docker-compose.sftp.yml up -d

legacy-sftp-down: ## Stop the SFTP drop fixture
	docker compose -f etl/legacy-extra/docker-compose.sftp.yml down

# --- Functional-equivalence gate for source-level security refactors ---
#
# security/equivalence/findings.yaml registers each finding (subject class,
# methods, secure pattern) and each module's emit/test commands. The recorded
# before-state lives in security/equivalence/expected/ and is fingerprinted
# against the cases, the seed, the emitter and the subject sources. Reports land
# in security/equivalence/reports/ (git-ignored: collect them as CI artifacts and
# paste the summary into the PR).

EQ := uv run --with pyyaml==6.0.2 --with tabulate==0.10.0 --with defusedxml==0.7.1 security/equivalence/harness/equivalence_check.py

eq-list: ## List the registered findings and the state of their recorded evidence
	$(EQ) list

eq-gate: ## Grade every finding against its recorded evidence, before-state or refactored
	$(EQ) grade --stage auto $(if $(FINDING),--finding $(FINDING),)

eq-baseline: ## Prove the recorded before-state still reproduces (FINDING=<id> optional)
	$(EQ) grade --stage baseline $(if $(FINDING),--finding $(FINDING),)

eq-verify: ## Grade a refactor: contract cases unchanged, attacks neutralised (FINDING=<id> optional)
	$(EQ) grade --stage remediated $(if $(FINDING),--finding $(FINDING),)

eq-exploit: ## Report whether the attack cases still fire, ignoring the recording
	$(EQ) exploit $(if $(FINDING),--finding $(FINDING),)

eq-exploit-refactored: ## Require a closed exploit verdict from every finding whose subject changed
	$(EQ) exploit --refactored-only $(if $(FINDING),--finding $(FINDING),)

eq-tests: ## Run the affected module's own suite against the recorded pass list
	$(EQ) tests $(if $(FINDING),--finding $(FINDING),)

eq-record: ## Record the before-state as the reference evidence (REASON="..." required)
	@test -n "$(REASON)" || (echo 'REASON is required, e.g. make eq-record REASON="baseline before OW-SEC-401 refactor"' >&2; exit 2)
	$(EQ) record --reason "$(REASON)" $(if $(FINDING),--finding $(FINDING),) $(if $(ALLOW_RERECORD),--allow-rerecord,)
