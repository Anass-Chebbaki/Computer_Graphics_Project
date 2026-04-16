#!/bin/bash
# ============================================================================
# Ollama Installation Guide
# ============================================================================
# Questo script guida l'installazione di Ollama e il download del modello LLM
# Documentazione: https://ollama.ai
#
# Prerequisiti:
#  - Connessione a Internet
#  - ~9GB di spazio disco per il modello llama3
#  - Windows: PowerShell con privilegi amministrativi
#
# Nota: Ollama verrà avviato in un terminale separato dopo l'installazione
# ============================================================================

set -e  # Esci se un comando fallisce

echo "[INFO] Ollama Installation Script"
echo "[INFO] ===================================================="
echo ""

# ============================================================================
# STEP 1: Determinare il Sistema Operativo e Installare Ollama
# ============================================================================
echo "[STEP 1] Rilevamento del sistema operativo..."
echo ""

case "$(uname -s)" in
  Linux*)
    echo "[INFO] Sistema rilevato: Linux"
    echo "[ACTION] Esecuzione dello script di installazione ufficiale..."
    curl -fsSL https://ollama.com/install.sh | sh
    OLLAMA_BIN="ollama"
    ;;
  Darwin*)
    echo "[INFO] Sistema rilevato: macOS"
    echo "[ACTION] Installazione tramite Homebrew..."
    if ! command -v brew &> /dev/null; then
      echo "[ERROR] Homebrew non trovato. Visitare: https://brew.sh"
      exit 1
    fi
    brew install ollama
    OLLAMA_BIN="ollama"
    ;;
  *)
    echo "[WARNING] Sistema non riconosciuto tramite uname"
    echo "[INFO] Per Windows, eseguire in PowerShell (admin):"
    echo "        winget install Ollama.Ollama"
    echo ""
    exit 0
    ;;
esac

echo ""

# ============================================================================
# STEP 2: Verificare l'Installazione
# ============================================================================
echo "[STEP 2] Verifica dell'installazione..."
echo ""

if ! command -v $OLLAMA_BIN &> /dev/null; then
  echo "[ERROR] Ollama non trovato. Installazione fallita."
  echo "[HINT] Aggiungere Ollama al PATH o riavviare il terminale."
  exit 1
fi

echo "[OK] Ollama installato:"
$OLLAMA_BIN --version
echo ""

# ============================================================================
# STEP 3: Avviare il Server Ollama
# ============================================================================
echo "[STEP 3] Avvio del server Ollama..."
echo ""
echo "[ACTION] APRI UN NUOVO TERMINALE e esegui:"
echo "          ollama serve"
echo ""
echo "[INFO] Il server rimane in ascolto su: http://localhost:11434"
echo "[INFO] Premi Ctrl+C nel terminale della pipeline per continuare il setup"
echo ""
read -p "Premi INVIO una volta che il server Ollama è avviato..."
echo ""

# ============================================================================
# STEP 4: Scaricare il Modello LLM
# ============================================================================
echo "[STEP 4] Download del modello llama3..."
echo ""
echo "[INFO] Questa operazione richiede ~9GB di spazio disco"
echo "[INFO] La prima esecuzione potrebbe richiedere alcuni minuti"
echo ""

$OLLAMA_BIN pull llama3

echo ""
echo "[OK] Modello scaricato e disponibile"
echo ""

# ============================================================================
# STEP 5: Verifica del Server
# ============================================================================
echo "[STEP 5] Verifica della connessione al server..."
echo ""

if command -v curl &> /dev/null; then
  if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "[OK] Server Ollama risponde correttamente"
    echo "[INFO] Modelli disponibili:"
    curl -s http://localhost:11434/api/tags | jq '.models[].name' 2>/dev/null || curl -s http://localhost:11434/api/tags
  else
    echo "[ERROR] Server Ollama non raggiungibile"
    echo "[HINT] Assicurarsi che 'ollama serve' sia avviato in un terminale separato"
    exit 1
  fi
else
  echo "[WARNING] curl non disponibile, omessa verifica della connessione"
fi

echo ""
echo "[STEP 6] Configurazione completata"
echo "[SUCCESS] Ollama è pronto per l'uso nel progetto!"
echo ""