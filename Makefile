# Two-terminal development without Docker. Run `make help`. Every port, host and URL comes from an environment variable with the default shown here.
VENV            ?= .venv
CDI_API_HOST    ?= 127.0.0.1
CDI_API_PORT    ?= 8000
CDI_WEB_HOST    ?= 127.0.0.1
CDI_WEB_PORT    ?= 5173
# The repository to analyse (a checkout with .cdi/config.yml). Default: the current directory, which has none: set it.
CDI_TARGET      ?= .
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

.PHONY: help setup test test-backend test-web e2e audit baseline pr serve web web-preview smoke sample-baseline sample-pr sample-serve

help:           ## list the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/^([a-z-]+):.*## (.*)/  make \1\t\2/'
	@echo; echo "Variables (defaults): VENV=$(VENV) CDI_TARGET=$(CDI_TARGET) CDI_API_HOST=$(CDI_API_HOST) CDI_API_PORT=$(CDI_API_PORT) CDI_WEB_HOST=$(CDI_WEB_HOST) CDI_WEB_PORT=$(CDI_WEB_PORT)"

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
