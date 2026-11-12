# Run `make help`. Quick start (each command installs what it needs the first time):
#   make run          the read-only API and the graph explorer together for CDI_TARGET (needs its .cdi/config.yml)
#   make api / make ui  the same, one per terminal.   make neo4j  optional Neo4j (see `make help`).
# Every port, host and URL comes from an environment variable with the default shown here.
VENV            ?= .venv
CDI_API_HOST    ?= 127.0.0.1
CDI_API_PORT    ?= 8000
CDI_WEB_HOST    ?= 127.0.0.1
CDI_WEB_PORT    ?= 5173
# The repository to analyse (a checkout with .cdi/config.yml). Default: the sample application next to this repository.
CDI_TARGET      ?= ../cdi-sample-app
# Baseline store: json (default, a file) or neo4j (optional, `make neo4j` starts it).
STORE           ?= json
NEO4J_BOLT_PORT ?= 7688
NEO4J_HTTP_PORT ?= 7475
# Branch or sha for `make pr`
PR              ?=
# The sample application checkout used by the sample-* shortcuts
SAMPLE          ?= ../cdi-sample-app

PY  := $(abspath $(VENV))/bin/python
CDI := $(abspath $(VENV))/bin/cdi
TARGET := $(abspath $(CDI_TARGET))
# The API may be called by exactly the page started by `make web` (an explicit origin, never '*'); add more via CDI_CORS_ORIGINS.
WEB_ORIGIN := http://$(CDI_WEB_HOST):$(CDI_WEB_PORT)
export CDI_API_HOST CDI_API_PORT CDI_WEB_HOST CDI_WEB_PORT
# STORE=neo4j: point every cdi command at the local Neo4j (the password is read from .local/neo4j-password, never stored in the repo).
ifeq ($(STORE),neo4j)
export CDI__graph__store := neo4j
export CDI__graph__neo4j__uri := bolt://127.0.0.1:$(NEO4J_BOLT_PORT)
NEO4J_PASSWORD_CMD := $$(cat $(abspath .local/neo4j-password))
endif
READY := $(VENV)/.cdi-ready

.PHONY: help setup run api ui test test-backend test-web e2e audit baseline pr serve web web-preview smoke sample-baseline sample-pr sample-serve neo4j neo4j-stop neo4j-reset neo4j-browser

help:           ## list the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/^([a-z-]+):.*## (.*)/  make \1\t\2/'
	@echo; echo "Variables (defaults): VENV=$(VENV) CDI_TARGET=$(CDI_TARGET) CDI_API_HOST=$(CDI_API_HOST) CDI_API_PORT=$(CDI_API_PORT) CDI_WEB_HOST=$(CDI_WEB_HOST) CDI_WEB_PORT=$(CDI_WEB_PORT)"

# ---- one command each: they install or build whatever is missing, then run ----
$(READY): backend/requirements.txt backend/pyproject.toml frontend/package-lock.json backend/scanners/ts-morph/package-lock.json
	VENV=$(VENV) backend/scripts/setup.sh
	@touch $@

run: $(READY)   ## EVERYTHING for CDI_TARGET: baseline if missing, then the API and the explorer together (Ctrl-C stops both)
	$(MAKE) -j2 api ui

api: $(READY)   ## the read-only API for CDI_TARGET on CDI_API_PORT; builds the baseline first if there is none (STORE=neo4j: starts Neo4j and loads it)
ifeq ($(STORE),neo4j)
	$(MAKE) neo4j
	NEO4J_PASSWORD=$(NEO4J_PASSWORD_CMD) $(MAKE) baseline
else
	@test -f "$(TARGET)/out/baseline.json" || $(MAKE) baseline
endif
	$(if $(filter neo4j,$(STORE)),NEO4J_PASSWORD=$(NEO4J_PASSWORD_CMD) )$(MAKE) serve

ui: $(READY)    ## the graph explorer on CDI_WEB_PORT (start `make api` too, or use `make run`)
	$(MAKE) web

# ---- optional Neo4j (the default store is a JSON file; nothing needs Neo4j) ----
neo4j:          ## start a local Neo4j in Docker (browser on NEO4J_HTTP_PORT, bolt on NEO4J_BOLT_PORT); password saved in .local/
	@command -v docker >/dev/null || { echo "Docker is not installed: install Docker Desktop, start it, run again"; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "Docker is not running: start Docker Desktop and run again"; exit 1; }
	@mkdir -p .local && { test -s .local/neo4j-password || ( umask 077; echo "Aa1-$$(openssl rand -hex 12)" > .local/neo4j-password ); }
	NEO4J_PASSWORD=$$(cat .local/neo4j-password) docker compose -p cdi-poc -f backend/deploy/neo4j-compose.yml up -d --wait
	@echo "Neo4j ready. Browser: http://$(CDI_API_HOST):$(NEO4J_HTTP_PORT)  user neo4j  password in .local/neo4j-password. Load the graph: make baseline STORE=neo4j"

neo4j-stop:     ## stop Neo4j (data is kept)
	NEO4J_PASSWORD=x docker compose -p cdi-poc -f backend/deploy/neo4j-compose.yml stop

neo4j-reset:    ## DELETE the Neo4j container, its data and the saved password
	NEO4J_PASSWORD=x docker compose -p cdi-poc -f backend/deploy/neo4j-compose.yml down -v
	rm -f .local/neo4j-password

setup:          ## once: venv, backend (pip install -e backend), .NET scanners, npm ci (scanner + frontend)
	VENV=$(VENV) backend/scripts/setup.sh

test: test-backend test-web  ## backend (pytest) and frontend (vitest) unit tests; no Neo4j needed

test-backend:   ## pytest (Neo4j tests skip without NEO4J_PASSWORD)
	cd backend && $(PY) -m pytest -q

test-web:       ## vitest + typecheck
	cd frontend && npx tsc --noEmit -p . && npm test

e2e:            ## Playwright smoke tests (snapshot, live API, live API with token)
	cd frontend && CDI_BIN=$(CDI) npm run test:e2e

audit:          ## fail if sample-specific names appear in backend/ or frontend/ source
	$(CDI) audit

baseline:       ## build the baseline of CDI_TARGET (JSON file out/baseline.json inside it)
	@test -f "$(TARGET)/.cdi/config.yml" || { echo "CDI_TARGET must point at a repository that has .cdi/config.yml (now: $(TARGET))"; exit 2; }
	cd "$(TARGET)" && $(CDI) baseline full

pr:             ## analyse a pull request of CDI_TARGET locally: make pr PR=<branch>
	@test -n "$(PR)" || { echo "usage: make pr PR=<branch-or-sha> [CDI_TARGET=...]"; exit 2; }
	cd "$(TARGET)" && $(CDI) pr --pr "$(PR)"

serve:          ## terminal 1: the read-only API for CDI_TARGET (optional token: export CDI_API_TOKEN=...)
	@test -f "$(TARGET)/.cdi/config.yml" || { echo "CDI_TARGET must point at a repository that has .cdi/config.yml (now: $(TARGET))"; exit 2; }
	cd "$(TARGET)" && $(CDI) serve --host $(CDI_API_HOST) --port $(CDI_API_PORT) --cors-origin $(WEB_ORIGIN) $(SERVE_ARGS)

web:            ## terminal 2: the explorer dev server, talking to the API of terminal 1
	cd frontend && CDI_API_BASE_URL=http://$(CDI_API_HOST):$(CDI_API_PORT) npm run dev

web-preview:    ## terminal 2 alternative: production build + preview server
	cd frontend && npm run build && CDI_API_BASE_URL=http://$(CDI_API_HOST):$(CDI_API_PORT) npm run preview

smoke:          ## end-to-end check on free ports: baseline, PR run, API, frontend, then clean shutdown (CDI_SAMPLE_REPO=path to use the sample repo)
	$(PY) backend/scripts/smoke.py

sample-baseline: ## shortcut: baseline of the sample app checkout (SAMPLE=../cdi-sample-app)
	$(MAKE) baseline CDI_TARGET=$(SAMPLE)

sample-pr:      ## shortcut: impact report of a branch of the sample app: make sample-pr PR=<branch>
	$(MAKE) pr CDI_TARGET=$(SAMPLE) PR=$(PR)

sample-serve:   ## shortcut: terminal 1, the read-only API over the sample app's baseline (terminal 2: make web)
	$(MAKE) serve CDI_TARGET=$(SAMPLE)
