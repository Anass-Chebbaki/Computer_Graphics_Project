#!/bin/bash
# ============================================================
# Setup Computer_Graphics_Project
# ============================================================

# ============================================================
# PASSO 1 — Creare la struttura directory mancanti
# ============================================================
mkdir -p tests/fixtures
mkdir -p assets/renders
mkdir -p docs
mkdir -p .github/ISSUE_TEMPLATE

# ============================================================
# PASSO 2 — Ambiente Python
# ============================================================
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
# .venv\Scripts\activate        # Windows

pip install --upgrade pip
pip install -e ".[dev]"

# ============================================================
# PASSO 3 — Installare Ollama
# ============================================================
# Linux:
curl -fsSL https://ollama.com/install.sh | sh

# Windows (PowerShell admin):
# winget install Ollama.Ollama

# macOS:
# brew install ollama

# Avviare il server (terminale separato)
ollama serve

# Scaricare il modello
ollama pull llama3

# Verificare
curl http://localhost:11434/api/tags

# ============================================================
# PASSO 4 — Configurazione
# ============================================================
cp .env.example .env

# ============================================================
# PASSO 5 — Pre-commit hooks
# ============================================================
pre-commit install
pre-commit run --all-files

# ============================================================
# PASSO 6 — Eseguire i test
# ============================================================
make test

# ============================================================
# PASSO 7 — Prima esecuzione della pipeline
# ============================================================
make demo

# ============================================================
# PASSO 8 — Costruire la scena in Blender
# ============================================================
# Aggiungere asset .obj nella cartella assets/models/
# (table.obj, chair.obj, lamp.obj ecc.)
make blender-render

# ============================================================
# PASSO 9 — Pubblicare su GitHub
# ============================================================
# git init (già fatto)
# git add .
# git commit -m "feat: setup complete"
# git branch -M main
# git remote add origin https://github.com/TUOUSERNAME/Computer_Graphics_Project.git
# git push -u origin main
