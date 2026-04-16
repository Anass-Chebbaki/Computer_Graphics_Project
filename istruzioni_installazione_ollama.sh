# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Windows (PowerShell come amministratore)
winget install Ollama.Ollama

# macOS
brew install ollama

# Verificare l'installazione
ollama --version

# Avviare il server Ollama (lasciare aperto in un terminale separato)
ollama serve

# In un altro terminale, scaricare il modello
ollama pull llama3

# Verifica che il server risponda
curl http://localhost:11434/api/tags