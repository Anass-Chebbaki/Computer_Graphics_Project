#!/bin/bash
# ============================================================
# Entrypoint Docker per NL2Scene3D
# ============================================================

set -e

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}╔══════════════════════════════════╗${NC}"
echo -e "${GREEN}║      NL2Scene3D Pipeline         ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════╝${NC}"
echo ""

# Configurazione
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-llama3}"
MAX_RETRIES="${MAX_RETRIES:-3}"
OUTPUT_FILE="${OUTPUT_FILE:-/app/output/scene_objects.json}"
MAX_WAIT_SECONDS=120

echo -e "${YELLOW}Configurazione:${NC}"
echo "  Ollama URL: ${OLLAMA_URL}"
echo "  Modello:    ${OLLAMA_MODEL}"
echo "  Output:     ${OUTPUT_FILE}"
echo ""

# ─────────────────────────────────────────────
# Attendi che Ollama sia pronto
# ─────────────────────────────────────────────
echo -e "${YELLOW}Attesa server Ollama...${NC}"
waited=0
until curl -sf "${OLLAMA_URL}/api/tags" > /dev/null 2>&1; do
    if [ $waited -ge $MAX_WAIT_SECONDS ]; then
        echo -e "${RED}ERRORE: Ollama non risponde dopo ${MAX_WAIT_SECONDS}s${NC}"
        exit 1
    fi
    echo "  Attesa... (${waited}s / ${MAX_WAIT_SECONDS}s)"
    sleep 5
    waited=$((waited + 5))
done
echo -e "${GREEN}✓ Ollama è pronto${NC}"
echo ""

# ─────────────────────────────────────────────
# Scarica il modello se non presente
# ─────────────────────────────────────────────
echo -e "${YELLOW}Verifica modello ${OLLAMA_MODEL}...${NC}"
if ! curl -sf "${OLLAMA_URL}/api/tags" | python3 -c "
import json, sys
data = json.load(sys.stdin)
models = [m['name'] for m in data.get('models', [])]
target = '${OLLAMA_MODEL}'
# Controlla match esatto o con tag :latest
found = any(m == target or m.startswith(target + ':') for m in models)
sys.exit(0 if found else 1)
" 2>/dev/null; then
    echo "  Modello non trovato. Download in corso..."
    ollama pull "${OLLAMA_MODEL}" || {
        echo -e "${RED}ERRORE: Impossibile scaricare il modello ${OLLAMA_MODEL}${NC}"
        exit 1
    }
    echo -e "${GREEN}✓ Modello scaricato${NC}"
else
    echo -e "${GREEN}✓ Modello già disponibile${NC}"
fi
echo ""

# ─────────────────────────────────────────────
# Crea directory di output
# ─────────────────────────────────────────────
mkdir -p "$(dirname "${OUTPUT_FILE}")"

# ─────────────────────────────────────────────
# Esegui la pipeline
# ─────────────────────────────────────────────
echo -e "${YELLOW}Avvio pipeline NL2Scene3D...${NC}"
echo ""

exec python scripts/run_pipeline.py \
    --model "${OLLAMA_MODEL}" \
    --output "${OUTPUT_FILE}" \
    --retries "${MAX_RETRIES}" \
    --ollama-url "${OLLAMA_URL}" \
    "$@"