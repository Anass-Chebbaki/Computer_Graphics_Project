.PHONY: help install install-dev lint format type-check test test-cov check-coverage \
        clean docker-build docker-up docker-down ollama-start \
        ollama-pull pipeline demo

PYTHON := python
PIP    := pip
PYTEST := pytest
RUFF   := ruff
BLACK  := black
MYPY   := mypy

MODEL  ?=
OUTPUT ?= scene_objects.json

# Utility per passare il modello solo se definito
MODEL_ARG = $(if $(MODEL),--model $(MODEL),)

# ---------------------------------------------------------------------------
# Aiuto
# ---------------------------------------------------------------------------
help: ## Mostra questo help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Installazione
# ---------------------------------------------------------------------------
install: ## Installa le dipendenze di produzione
	$(PIP) install -e .

install-dev: ## Installa tutte le dipendenze (incluse quelle di sviluppo)
	$(PIP) install -e ".[dev]"
	pre-commit install

# ---------------------------------------------------------------------------
# Qualità del codice
# ---------------------------------------------------------------------------
lint: ## Esegue ruff linter
	$(RUFF) check src/ tests/ scripts/

format: ## Formatta il codice con black e ruff
	$(BLACK) src/ tests/ scripts/
	$(RUFF) check --fix src/ tests/ scripts/

type-check: ## Controllo tipi con mypy
	$(MYPY) src/computer_graphics/ --ignore-missing-imports

# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------
test: ## Esegue i test
	$(PYTEST) tests/ -v

test-cov: ## Esegue i test con coverage HTML
	$(PYTEST) tests/ -v --cov=src/computer_graphics \
		--cov-report=term-missing \
		--cov-report=html:htmlcov
	@echo "Report coverage: htmlcov/index.html"

check-coverage: ## Verifica che il coverage rispetti i threshold (90% globale, 85% per file)
	$(PYTHON) scripts/check_coverage.py

# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------
ollama-start: ## Avvia il server Ollama in background
	ollama serve &
	@echo "Server Ollama avviato su http://localhost:11434"

ollama-pull: ## Scarica il modello specificato in MODEL
	ollama pull $(MODEL)

ollama-status: ## Verifica lo stato del server Ollama
	curl -s http://localhost:11434/api/tags | python -m json.tool

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
pipeline: ## Esegue la pipeline con descrizione interattiva
	$(PYTHON) scripts/run_pipeline.py --interactive $(MODEL_ARG) --output $(OUTPUT)

demo: ## Demo rapida con descrizione hardcoded
	$(PYTHON) scripts/run_pipeline.py \
		"una stanza con un tavolo al centro, una sedia davanti al tavolo e una lampada nell angolo" \
		$(MODEL_ARG) \
		--output $(OUTPUT)

blender-run: ## Avvia Blender con lo script di costruzione scena
	blender --background --python scripts/blender_runner.py -- $(OUTPUT)

blender-render: ## Avvia Blender con render
	blender --background --python scripts/blender_runner.py -- $(OUTPUT) --render assets/renders/output.png

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------
docker-build: ## Costruisce l'immagine Docker
	docker build -f docker/Dockerfile -t computer-graphics:latest .

docker-up: ## Avvia tutti i servizi con Docker Compose
	docker compose up --build

docker-down: ## Ferma i servizi Docker
	docker compose down

docker-logs: ## Mostra i log dei container
	docker compose logs -f

# ---------------------------------------------------------------------------
# Pulizia
# ---------------------------------------------------------------------------
clean: ## Rimuove file temporanei e cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "Pulizia completata."

# ---------------------------------------------------------------------------
# Asset
# ---------------------------------------------------------------------------
generate-primitives: ## Genera asset 3D primitivi con Blender
	blender --background --python scripts/generate_primitives.py

check-assets: ## Verifica lo stato della libreria di asset
	$(PYTHON) scripts/setup_assets.py check

asset-report: ## Genera report JSON degli asset
	$(PYTHON) scripts/setup_assets.py report

# ---------------------------------------------------------------------------
# CLI diretta (dopo pip install -e .)
# ---------------------------------------------------------------------------
cli-check: ## Verifica prerequisiti via CLI
	computer-graphics check

cli-info: ## Mostra configurazione via CLI
	computer-graphics info

cli-demo: ## Demo via CLI
	computer-graphics generate \
		"una stanza con un tavolo al centro, una sedia davanti, una lampada nell angolo e un divano" \
		--output $(OUTPUT)

cli-validate: ## Valida il JSON di output corrente
	computer-graphics validate $(OUTPUT)

# ---------------------------------------------------------------------------
# Benchmark / Performance
# ---------------------------------------------------------------------------
benchmark: ## Esegue il benchmark della pipeline (5 run)
	@echo "Benchmark pipeline NL2Scene3D (5 esecuzioni)..."
	@for i in 1 2 3 4 5; do \
		echo "Run $$i/5:"; \
		time $(PYTHON) scripts/run_pipeline.py \
			"una stanza con tavolo e sedia" \
			--output /tmp/bench_output.json 2>/dev/null || true; \
	done

# ---------------------------------------------------------------------------
# Report coverage HTML aperto nel browser
# ---------------------------------------------------------------------------
coverage-open: test-cov ## Apre il report coverage nel browser
	@python -m webbrowser htmlcov/index.html

# ---------------------------------------------------------------------------
# Documentazione
# ---------------------------------------------------------------------------
docs-serve: ## Serve la documentazione localmente (richiede mkdocs)
	@mkdocs serve 2>/dev/null || \
		python -m http.server 8080 --directory docs/
