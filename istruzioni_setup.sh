#!/bin/bash
# ============================================================================
# Computer Graphics Project — Complete Setup Script
# ============================================================================
# Questo script automatizza l'intero processo di setup del progetto.
#
# Requisiti di Sistema:
#  - Python 3.10+ (verifica via: python --version)
#  - pip (Python package manager)
#  - git (verifica via: git --version)
#  - ~12GB di spazio disco (incluso modello Ollama)
#  - Connessione a Internet
#
# Piattaforme Supportate:
#  - Linux (Ubuntu 20.04+, Debian 11+)
#  - macOS (10.15+)
#  - Windows (PowerShell 5.1+, eseguire come amministratore)
#
# Esecuzione:
#  bash istruzioni_setup.sh          (automatico)
#  bash istruzioni_setup.sh --help   (mostra questa guida)
# ============================================================================

set -e  # Esci se un comando fallisce
set -o pipefail  # Esci se un comando in una pipe fallisce

# ============================================================================
# Colori per l'output
# ============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'  # No Color

# ============================================================================
# Funzioni Helper
# ============================================================================
log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

log_ok() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# ============================================================================
# STEP 0: Prerequisiti
# ============================================================================
log_step "Verifica dei prerequisiti..."
echo ""

if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    log_error "Python 3 non trovato. Installare da: https://python.org"
    exit 1
fi
log_ok "Python trovato"

if ! command -v git &> /dev/null; then
    log_error "git non trovato. Installare da: https://git-scm.com"
    exit 1
fi
log_ok "Git trovato"

echo ""

# ============================================================================
# STEP 1: Creare la Struttura Directory
# ============================================================================
log_step "Creazione della struttura directory..."
echo ""

mkdir -p tests/fixtures
log_ok "tests/fixtures/"

mkdir -p assets/renders
log_ok "assets/renders/"

mkdir -p assets/models
log_ok "assets/models/"

mkdir -p docs
log_ok "docs/"

mkdir -p .github/ISSUE_TEMPLATE
log_ok ".github/ISSUE_TEMPLATE/"

echo ""

# ============================================================================
# STEP 2: Configurare l'Ambiente Python Virtuale
# ============================================================================
log_step "Configurazione dell'ambiente Python virtuale..."
echo ""

if [ ! -d ".venv" ]; then
    log_info "Creazione del virtual environment..."
    python -m venv .venv || python3 -m venv .venv
    log_ok "Virtual environment creato in: .venv/"
else
    log_warning "Virtual environment già esistente: .venv/"
fi

echo ""
log_info "Attivazione del virtual environment..."
echo ""

if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
else
    log_error "Impossibile trovare lo script di attivazione del venv"
    exit 1
fi

log_ok "Virtual environment attivato"
echo ""

# ============================================================================
# STEP 3: Installare le Dipendenze Python
# ============================================================================
log_step "Installazione delle dipendenze Python..."
echo ""

log_info "Aggiornamento di pip, setuptools, wheel..."
pip install --quiet --upgrade pip setuptools wheel
log_ok "Strumenti di build aggiornati"

echo ""
log_info "Installazione del progetto in modalità sviluppo..."
log_info "Questo includerà dipendenze di produzione E sviluppo"
pip install -e ".[dev]"

echo ""
log_ok "Dipendenze installate correttamente"
echo ""

# ============================================================================
# STEP 4: Installare Ollama
# ============================================================================
log_step "Setup di Ollama e modello LLM..."
echo ""

if command -v ollama &> /dev/null; then
    log_warning "Ollama è già installato"
    ollama --version
else
    log_info "Ollama non trovato. Eseguire manualmente:"
    echo ""
    uname_out=$(uname -s)
    case "$uname_out" in
        Linux*)
            echo "  Linux:"
            echo "    curl -fsSL https://ollama.com/install.sh | sh"
            ;;
        Darwin*)
            echo "  macOS:"
            echo "    brew install ollama"
            ;;
        *)
            echo "  Windows (PowerShell admin):"
            echo "    winget install Ollama.Ollama"
            ;;
    esac
    echo ""
    log_warning "Una volta installato, eseguire in un terminale separato:"
    echo "  ollama serve"
    echo ""
    log_warning "Completare il setup di Ollama prima di continuare"
    read -p "Premi INVIO dopo l'installazione di Ollama... "
fi

echo ""

# ============================================================================
# STEP 5: Configurazione dell'Ambiente
# ============================================================================
log_step "Configurazione dell'ambiente..."
echo ""

if [ -f ".env.example" ]; then
    if [ ! -f ".env" ]; then
        cp .env.example .env
        log_ok "File .env creato da .env.example"
        log_info "Modificare .env secondo le proprie esigenze"
    else
        log_warning "File .env già presente, saltato"
    fi
else
    log_warning "File .env.example non trovato"
fi

echo ""

# ============================================================================
# STEP 6: Configurare Pre-commit Hooks
# ============================================================================
log_step "Configurazione dei pre-commit hooks..."
echo ""

if command -v pre-commit &> /dev/null; then
    pre-commit install
    log_ok "Pre-commit hooks installati"

    echo ""
    log_info "Esecuzione del primo check su tutti i file..."
    pre-commit run --all-files || log_warning "Alcuni file potrebbero richiedere aggiornamenti"
else
    log_warning "pre-commit non disponibile (dovrebbe essere installato tramite pip install -e .[dev])"
fi

echo ""

# ============================================================================
# STEP 7: Eseguire i Test Automatizzati
# ============================================================================
log_step "Esecuzione dei test automatizzati..."
echo ""

if command -v pytest &> /dev/null; then
    log_info "Esecuzione di pytest..."
    pytest tests/ -v --tb=short || log_error "Alcuni test sono falliti"
    log_ok "Test completati"
else
    log_warning "pytest non trovato. Assicurarsi che dipendenze dev siano installate"
fi

echo ""

# ============================================================================
# STEP 8: Verifica della Qualità del Codice (Opzionale)
# ============================================================================
log_step "Verifica della qualità del codice (linting, type checking)..."
echo ""

if command -v ruff &> /dev/null; then
    log_info "Esecuzione di ruff check..."
    ruff check src/ tests/ scripts/ && log_ok "Ruff check passato" || log_warning "Ruff ha trovato problemi"
else
    log_warning "ruff non trovato"
fi

if command -v mypy &> /dev/null; then
    log_info "Esecuzione di mypy (type checking)..."
    mypy src/computer_graphics/ --ignore-missing-imports && log_ok "Type checking passato" || log_warning "MyPy ha trovato problemi"
else
    log_warning "mypy non trovato"
fi

echo ""

# ============================================================================
# STEP 9: Prossimi Passi
# ============================================================================
log_step "Setup completato con successo!"
echo ""
log_ok "Ambiente pronto per lo sviluppo"
echo ""
echo "[PROSSIMI PASSI]"
echo ""
echo "1. OLLAMA:"
echo "   Assicurarsi che 'ollama serve' sia in esecuzione:"
echo "     ollama serve"
echo ""
echo "2. PIPELINE DEMO:"
echo "   Eseguire il primo test della pipeline:"
echo "     ./scripts/run_pipeline.py --description \"a wooden table with a chair\""
echo ""
echo "3. BLENDER (opzionale):"
echo "   Aggiungere modelli 3D in: assets/models/"
echo "   Quindi eseguire:"
echo "     ./scripts/blender_runner.py output/scene.json"
echo ""
echo "4. DOCUMENTAZIONE:"
echo "   Consultare README.md per informazioni dettagliate"
echo ""
echo "[HINT] Mantenere attivo il virtual environment:"
echo "   source .venv/bin/activate  (Linux/macOS)"
echo "   .venv\\\\Scripts\\\\activate   (Windows)"
echo ""
