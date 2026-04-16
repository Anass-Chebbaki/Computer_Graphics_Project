# NL2Scene3D

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

NL2Scene3D Ã¨ una pipeline automatizzata che converte descrizioni testuali in linguaggio naturale in scene 3D complete all'interno di Blender. Il sistema utilizza modelli linguistici di grandi dimensioni (LLM) eseguiti localmente tramite Ollama per interpretare la descrizione dell'utente, generare un layout spaziale strutturato in formato JSON e applicarlo programmaticamente a una scena Blender tramite l'API `bpy`.

Il progetto Ã¨ progettato per funzionare interamente in locale, senza dipendenze da servizi cloud o API esterne a pagamento.

---

## Indice

- [Architettura della pipeline](#architettura-della-pipeline)
- [Struttura del repository](#struttura-del-repository)
- [Requisiti](#requisiti)
- [Installazione](#installazione)
- [Configurazione](#configurazione)
- [Utilizzo](#utilizzo)
- [Riferimento CLI](#riferimento-cli)
- [Asset 3D](#asset-3d)
- [Sviluppo](#sviluppo)
- [Test](#test)
- [Docker](#docker)
- [CI/CD](#cicd)
- [Risoluzione dei problemi](#risoluzione-dei-problemi)
- [Licenza](#licenza)

---

## Architettura della pipeline

La pipeline Ã¨ composta da cinque fasi sequenziali, ciascuna implementata in un modulo dedicato:

```
Descrizione testuale (linguaggio naturale)
          |
          v
  [1] InputHandler
      Normalizzazione e validazione del testo di input.
      Supporta input da stringa, terminale interattivo o file .txt.
          |
          v
  [2] PromptBuilder
      Costruzione del prompt di sistema e del payload per Ollama.
      Il prompt vincola il modello a rispondere esclusivamente
      con un array JSON strutturato secondo uno schema fisso.
          |
          v
  [3] OllamaClient
      Chiamata HTTP POST all'endpoint /api/chat del server Ollama locale.
      Gestisce timeout, retry su errori di rete e health check preliminare.
          |
          v
  [4] JSONParser + Validator
      Estrazione robusta del JSON dalla risposta del modello
      (parsing diretto, regex, pulizia aggressiva di markdown e commenti).
      Validazione di ogni oggetto con Pydantic e coercizione dei tipi.
          |
          v
  [5] SceneBuilder + Renderer (Blender / bpy)
      Pulizia della scena di default, configurazione di luci e camera,
      importazione degli asset 3D, posizionamento secondo le coordinate
      generate dal modello, render opzionale in PNG.
```

Il formato JSON intermedio prodotto dal modello e consumato da Blender segue questo schema:

```json
[
  {
    "name": "table",
    "x": 0.0,
    "y": 0.0,
    "z": 0.0,
    "rot_x": 0.0,
    "rot_y": 0.0,
    "rot_z": 0.0,
    "scale": 1.0
  }
]
```

Tutte le coordinate sono espresse in unitÃ  Blender (1 unitÃ  = 1 metro). Le rotazioni sono in radianti nel sistema Euler XYZ.

---

## Struttura del repository

```
nl2scene3d/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                 # Lint, test e type check su push/PR
│   │   ├── lint.yml               # Workflow dedicato alla qualità del codice
│   │   └── docker.yml             # Build e push immagine Docker su GHCR
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   └── PULL_REQUEST_TEMPLATE.md
├── assets/
│   ├── models/                    # Asset 3D (.obj, .fbx, .glb) — non versionati
│   └── renders/                   # Output PNG generati da Blender
├── config/
│   ├── settings.yaml              # Configurazione principale del progetto
│   └── prompts/
│       └── system_prompt.txt      # Prompt di sistema per il modello LLM
├── docs/
│   ├── architecture.md
│   ├── installation.md
│   ├── usage.md
│   └── contributing.md
├── src/
│   └── nl2scene3d/
│       ├── __init__.py
│       ├── input_handler.py       # Fase 1: gestione input utente
│       ├── prompt_builder.py      # Fase 2: costruzione payload Ollama
│       ├── ollama_client.py       # Fase 3: client HTTP per Ollama
│       ├── json_parser.py         # Fase 4: parsing robusto del JSON
│       ├── validator.py           # Fase 4: validazione con Pydantic
│       ├── orchestrator.py        # Coordinamento delle fasi 1-4
│       └── blender/
│           ├── __init__.py
│           ├── scene_builder.py   # Fase 5: costruzione scena in Blender
│           ├── asset_importer.py  # Importazione asset 3D
│           └── renderer.py        # Configurazione render e output
├── scripts/
│   ├── run_pipeline.py            # Entry point CLI principale
│   ├── blender_runner.py          # Script da eseguire dentro Blender
│   └── setup_assets.py            # Utility per configurare la libreria asset
├── tests/
│   ├── conftest.py                # Fixture condivise
│   ├── test_input_handler.py
│   ├── test_prompt_builder.py
│   ├── test_ollama_client.py
│   ├── test_json_parser.py
│   ├── test_validator.py
│   ├── test_orchestrator.py
│   └── fixtures/
│       ├── sample_response_clean.json
│       ├── sample_response_dirty.txt
│       └── sample_objects.json
├── docker/
│   ├── Dockerfile
│   ├── Dockerfile.blender
│   └── entrypoint.sh
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
├── docker-compose.yml
├── LICENSE
├── Makefile
├── pyproject.toml
├── README.md
└── CHANGELOG.md
```

---

## Requisiti

### Dipendenze di sistema

| Componente | Versione minima | Note |
|---|---|---|
| Python | 3.10 | Richiesto per `match`/`case` e type hints moderni |
| Blender | 4.0 | Necessario per la fase 5 (costruzione scena e render) |
| Ollama | Ultima stabile | Deve essere installato separatamente |
| Docker | 24.0 | Opzionale, necessario solo per la modalitÃ  containerizzata |
| Git | 2.40 | Per il versionamento e i pre-commit hook |

### Dipendenze Python (produzione)

| Pacchetto | Versione | Scopo |
|---|---|---|
| `requests` | >=2.31.0 | Comunicazione HTTP con il server Ollama |
| `pyyaml` | >=6.0.1 | Lettura della configurazione `settings.yaml` |
| `click` | >=8.1.7 | Interfaccia CLI |
| `rich` | >=13.7.0 | Output formattato a terminale, tabelle, spinner |
| `pydantic` | >=2.5.0 | Validazione e serializzazione degli oggetti scena |

### Dipendenze Python (sviluppo)

| Pacchetto | Versione | Scopo |
|---|---|---|
| `pytest` | >=7.4.0 | Framework di test |
| `pytest-cov` | >=4.1.0 | Coverage dei test |
| `pytest-mock` | >=3.12.0 | Mock per test unitari |
| `ruff` | >=0.1.9 | Linter veloce |
| `black` | >=23.12.0 | Formattatore del codice |
| `mypy` | >=1.8.0 | Controllo statico dei tipi |
| `pre-commit` | >=3.6.0 | Hook Git pre-commit |
| `responses` | >=0.25.0 | Mock delle chiamate HTTP nei test |

---

## Installazione

### Installazione di Ollama

Ollama Ã¨ l'unico componente che richiede installazione separata. Espone un server HTTP locale sulla porta 11434 che riceve le richieste di inferenza.

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**macOS:**
```bash
brew install ollama
```

**Windows (PowerShell con privilegi di amministratore):**
```powershell
winget install Ollama.Ollama
```

Dopo l'installazione, avviare il server in un terminale separato e scaricare il modello:

```bash
# Terminale 1: avvia il server (mantenerlo aperto durante tutta la sessione)
ollama serve

# Terminale 2: scarica il modello (operazione una-tantum, ~4 GB)
ollama pull llama3

# Verifica che il server risponda correttamente
curl http://localhost:11434/api/tags
```

Il server risponde sulla porta `11434`. Questa Ã¨ anche la porta configurata di default in `config/settings.yaml` e nel file `.env.example`.

Modelli alternativi supportati (con compromessi velocitÃ /qualitÃ ):

| Modello | Dimensione | Note |
|---|---|---|
| `llama3` | ~4 GB | Raccomandato, buon bilanciamento |
| `llama3:8b` | ~4 GB | Equivalente a llama3 |
| `mistral` | ~4 GB | Alternativa valida |
| `llama3:70b` | ~40 GB | Alta qualitÃ , richiede hardware dedicato |
| `phi3` | ~2 GB | Leggero, adatto a macchine con poca RAM |

### Installazione del progetto

```bash
# Clona il repository
git clone https://github.com/yourusername/nl2scene3d.git
cd nl2scene3d

# Crea e attiva l'ambiente virtuale Python
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate

# Aggiorna pip e installa il progetto con le dipendenze di sviluppo
pip install --upgrade pip
pip install -e ".[dev]"

# Installa i pre-commit hook
pre-commit install

# Copia il file di configurazione ambiente
cp .env.example .env
```

Verifica che l'installazione sia andata a buon fine:

```bash
# Esegui la suite di test
make test

# Verifica che Ollama sia raggiungibile
python -c "from nl2scene3d.ollama_client import OllamaClient; print(OllamaClient().health_check())"
```

---

## Configurazione

### File `.env`

Copiare `.env.example` in `.env` e modificare i valori secondo l'ambiente locale:

```dotenv
# URL del server Ollama
OLLAMA_URL=http://localhost:11434

# Modello LLM da utilizzare
OLLAMA_MODEL=llama3

# Timeout in secondi per la chiamata HTTP al modello
# Aumentare questo valore su hardware lento o con modelli grandi
OLLAMA_TIMEOUT=180

# Percorso alla directory degli asset 3D
ASSETS_DIR=./assets/models

# Directory di output per i render PNG
RENDER_OUTPUT_DIR=./assets/renders

# Numero massimo di tentativi in caso di JSON non valido
MAX_RETRIES=3

# Livello di log: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=INFO
```

### File `config/settings.yaml`

Il file YAML centralizza tutti i parametri di configurazione. I valori definiti nel file `.env` hanno precedenza sulle impostazioni YAML quando vengono caricati esplicitamente dallo script.

```yaml
ollama:
  url: "http://localhost:11434"
  model: "llama3"
  timeout: 180
  max_connection_retries: 3
  retry_delay: 2.0
  options:
    temperature: 0.2      # Bassa temperatura per output deterministico
    top_p: 0.9
    num_predict: 1024     # Limite massimo di token nella risposta

pipeline:
  max_retries: 3
  verbose: true

paths:
  assets_dir: "assets/models"
  render_output_dir: "assets/renders"
  prompt_file: "config/prompts/system_prompt.txt"

blender:
  render_engine: "CYCLES"   # Alternativa: BLENDER_EEVEE
  resolution_x: 1920
  resolution_y: 1080
  samples: 64
  camera_location: [7.0, -7.0, 5.0]

validation:
  min_description_length: 10
  max_description_length: 2000
  max_coordinate_value: 50.0
```

### Prompt di sistema

Il prompt di sistema in `config/prompts/system_prompt.txt` Ã¨ il componente piÃ¹ critico per la qualitÃ  dell'output. Istruisce il modello a rispondere esclusivamente con un array JSON valido secondo lo schema atteso. Il file puÃ² essere modificato per adattare il comportamento del modello senza modificare il codice sorgente.

Il `PromptBuilder` carica il prompt con questa prioritÃ :
1. Testo passato esplicitamente come argomento al costruttore
2. File specificato tramite il parametro `system_prompt_file`
3. File nel percorso convenzionale `config/prompts/system_prompt.txt`
4. Prompt di default hardcoded nel modulo `prompt_builder.py`

---

## Utilizzo

### Esecuzione rapida

```bash
# Demo con descrizione predefinita (non richiede input)
make demo

# ModalitÃ  interattiva: chiede la descrizione a terminale
make pipeline

# Costruzione scena in Blender senza render
make blender-run

# Costruzione scena in Blender con render PNG
make blender-render
```

### Utilizzo da riga di comando

Lo script `scripts/run_pipeline.py` gestisce le fasi 1-4 (input â†’ JSON) e salva il risultato in un file JSON. Lo script Blender `scripts/blender_runner.py` gestisce la fase 5 (JSON â†’ scena 3D).

```bash
# Descrizione passata come argomento
python scripts/run_pipeline.py "una cucina con tavolo, due sedie e un frigorifero"

# ModalitÃ  interattiva
python scripts/run_pipeline.py --interactive

# Lettura da file
python scripts/run_pipeline.py --file descrizione_scena.txt

# Con parametri espliciti
python scripts/run_pipeline.py \
  "una sala riunioni con scrivania, quattro sedie e una lampada" \
  --model mistral \
  --output sala_riunioni.json \
  --retries 5 \
  --ollama-url http://localhost:11434 \
  --verbose

# Costruzione scena in Blender dal JSON generato
blender --background --python scripts/blender_runner.py -- scene_objects.json

# Costruzione scena con render
blender --background --python scripts/blender_runner.py \
  -- scene_objects.json \
  --render assets/renders/output.png
```

### Utilizzo come libreria Python

```python
from nl2scene3d.orchestrator import generate_scene_objects
from nl2scene3d.ollama_client import OllamaClient

# Verifica che Ollama sia raggiungibile
client = OllamaClient()
if not client.health_check():
    raise RuntimeError("Ollama non Ã¨ raggiungibile. Eseguire: ollama serve")

# Esecuzione della pipeline
objects = generate_scene_objects(
    scene_description="una stanza con tavolo, sedia e lampada da terra",
    model="llama3",
    max_retries=3,
    ollama_url="http://localhost:11434",
    timeout=180,
    verbose=True,
)

# Ogni oggetto Ã¨ un'istanza Pydantic con accesso diretto agli attributi
for obj in objects:
    print(f"{obj.name}: x={obj.x:.2f}, y={obj.y:.2f}, z={obj.z:.2f}, scale={obj.scale:.2f}")

# Serializzazione in dizionario o JSON
import json
data = [obj.model_dump() for obj in objects]
print(json.dumps(data, indent=2))
```

### Utilizzo da Blender Text Editor

Per eseguire lo script direttamente dall'editor interno di Blender senza passare dal terminale:

1. Aprire Blender e accedere all'area **Text Editor**
2. Aprire il file `scripts/blender_runner.py`
3. Modificare la sezione `CONFIG` in cima al file:
   ```python
   OBJECTS_JSON_PATH: str = "/percorso/assoluto/scene_objects.json"
   ASSETS_DIR: str = "/percorso/assoluto/assets/models"
   RENDER_OUTPUT: str = "/percorso/assoluto/assets/renders/output.png"
   RENDER_ENABLED: bool = True
   ```
4. Premere **Run Script**

---

## Riferimento CLI

```
Utilizzo: python scripts/run_pipeline.py [OPZIONI] [DESCRIZIONE]

Argomenti:
  DESCRIZIONE           Testo della scena da generare (opzionale se si usa --interactive o --file)

Opzioni:
  -i, --interactive     Chiede la descrizione interattivamente a terminale
  -f, --file PATH       Legge la descrizione da un file .txt
  -m, --model TEXT      Nome del modello Ollama da usare  [default: llama3]
  -o, --output PATH     File JSON di output con gli oggetti generati  [default: scene_objects.json]
  -r, --retries INT     Numero massimo di tentativi in caso di JSON non valido  [default: 3]
  --ollama-url TEXT     URL del server Ollama  [default: http://localhost:11434]
  -v, --verbose         Abilita output di debug dettagliato
  --help                Mostra questo messaggio ed esce
```

```
Utilizzo: blender --background --python scripts/blender_runner.py -- [OPZIONI] JSON_PATH

Argomenti posizionali:
  JSON_PATH             Percorso al file JSON generato dalla pipeline

Opzioni:
  --render PATH         Abilita il render e salva il PNG nel percorso specificato
  --no-render           Disabilita il render (costruisce solo la scena)
```

Comandi Makefile disponibili:

```
install          Installa le dipendenze di produzione
install-dev      Installa tutte le dipendenze, incluse quelle di sviluppo
lint             Esegue ruff linter su src/, tests/, scripts/
format           Formatta il codice con black e ruff --fix
type-check       Controllo statico dei tipi con mypy
test             Esegue la suite di test con pytest
test-cov         Esegue i test con report di coverage HTML in htmlcov/
ollama-start     Avvia il server Ollama in background
ollama-pull      Scarica il modello specificato (default: llama3)
ollama-status    Mostra i modelli disponibili nel server locale
pipeline         Esegue la pipeline in modalitÃ  interattiva
demo             Esecuzione rapida con descrizione hardcoded di esempio
blender-run      Avvia Blender con lo script di costruzione scena
blender-render   Avvia Blender con costruzione scena e render PNG
docker-build     Costruisce l'immagine Docker
docker-up        Avvia tutti i servizi con Docker Compose
docker-down      Ferma i servizi Docker
docker-logs      Mostra i log dei container in tempo reale
clean            Rimuove file temporanei, cache e artefatti di build
```

---

## Asset 3D

La directory `assets/models/` deve contenere i modelli 3D da importare nella scena. Il sistema cerca i file con il nome corrispondente all'oggetto generato dal modello LLM nei formati seguenti, in ordine di prioritÃ :

1. `.obj` (Wavefront OBJ)
2. `.fbx` (Autodesk FBX)
3. `.glb` / `.gltf` (GL Transmission Format)

Il nome del file deve corrispondere esattamente al nome in inglese che il modello LLM restituisce nel campo `"name"` del JSON. Ad esempio, se il modello genera `"name": "table"`, il sistema cerca `assets/models/table.obj`.

| File asset | Oggetto corrispondente |
|---|---|
| `table.obj` | Tavolo |
| `chair.obj` | Sedia |
| `lamp.obj` | Lampada da terra |
| `desk.obj` | Scrivania |
| `sofa.obj` | Divano |
| `bookshelf.obj` | Libreria |
| `monitor.obj` | Monitor |
| `bed.obj` | Letto |

Se un asset non viene trovato, il sistema crea automaticamente un cubo proxy con materiale rosso semitrasparente e lo posiziona nelle coordinate previste. Questo comportamento permette di verificare il layout spaziale anche prima di disporre di tutti gli asset definitivi.

Fonti di modelli 3D gratuiti compatibili:
- [Poly Haven](https://polyhaven.com) â€” modelli in formato `.glb`, licenza CC0
- [Sketchfab](https://sketchfab.com/features/free-3d-models) â€” vari formati, licenze miste
- [BlendSwap](https://www.blendswap.com) â€” modelli nativi Blender
- [OpenGameArt](https://opengameart.org) â€” modelli in formati aperti, licenze libere

I file binari degli asset non sono inclusi nel repository. Per repository con modelli di grandi dimensioni, si consiglia di utilizzare [Git LFS](https://git-lfs.com).

---

## Sviluppo

### Workflow consigliato

```bash
# Attiva l'ambiente virtuale
source .venv/bin/activate

# Installa le dipendenze di sviluppo (se non giÃ  fatto)
make install-dev

# Installa i pre-commit hook
pre-commit install

# Ciclo di sviluppo standard
make lint          # Controlla lo stile del codice
make format        # Applica formattazione automatica
make type-check    # Controlla la correttezza dei tipi
make test          # Esegue i test
```

### Convenzioni di codice

Il progetto adotta le seguenti convenzioni:

- **Formattatore**: `black` con lunghezza riga massima di 88 caratteri
- **Linter**: `ruff` con i ruleset `E`, `F`, `W`, `I`, `N`, `UP`, `ANN`, `B`, `C4`, `SIM`
- **Type checking**: `mypy` in modalitÃ  strict per i moduli interni
- **Docstring**: stile Google per tutti i metodi pubblici
- **Annotazioni di tipo**: obbligatorie per tutte le funzioni pubbliche
- **Import**: ordinati con `isort` (integrato in ruff con ruleset `I`)

I pre-commit hook verificano automaticamente queste convenzioni prima di ogni commit. Per eseguire i controlli manualmente su tutti i file:

```bash
pre-commit run --all-files
```

### Struttura dei moduli

Ogni modulo corrisponde a una fase precisa della pipeline. I moduli nella directory `src/nl2scene3d/blender/` dipendono da `bpy` e possono essere importati solo all'interno del processo Blender. Non importarli in contesti Python standard: causeranno un `ImportError`.

Il modulo `orchestrator.py` Ã¨ il punto di coordinamento principale. Istanzia i componenti delle fasi 1-4, gestisce la logica di retry e produce la lista finale di `SceneObject` validati. Ãˆ il punto di ingresso raccomandato per l'utilizzo programmatico della pipeline.

---

## Test

### Esecuzione

```bash
# Suite completa
make test

# Con report di coverage a terminale e HTML
make test-cov

# Solo un modulo specifico
pytest tests/test_json_parser.py -v

# Solo una classe o un metodo
pytest tests/test_validator.py::TestValidateObjects::test_raises_on_empty_list -v

# Con output di log dettagliato
pytest tests/ -v --log-cli-level=DEBUG
```

### Organizzazione dei test

| File di test | Modulo testato | Tecnica principale |
|---|---|---|
| `test_input_handler.py` | `input_handler.py` | Test di validazione e factory method |
| `test_prompt_builder.py` | `prompt_builder.py` | Verifica struttura payload |
| `test_ollama_client.py` | `ollama_client.py` | Mock HTTP con `responses` |
| `test_json_parser.py` | `json_parser.py` | Input puliti e sporchi, casi limite |
| `test_validator.py` | `validator.py` | Validazione Pydantic, coercizione tipi |
| `test_orchestrator.py` | `orchestrator.py` | Test di integrazione con mock |

I moduli che dipendono da `bpy` (fase 5) non sono inclusi nella suite di test standard, poichÃ© richiedono un processo Blender attivo. Devono essere testati manualmente o tramite uno script di smoke test eseguito all'interno di Blender.

### Fixture

Le fixture condivise sono definite in `tests/conftest.py` e includono:

- `sample_clean_json`: output JSON ideale del modello, pronto per il parsing
- `sample_dirty_text`: testo con backtick markdown, commenti JavaScript e virgole finali (caso reale frequente)
- `valid_objects_list`: lista di dizionari giÃ  normalizzati per i test del validator
- `mock_ollama_response`: struttura JSON simulata della risposta HTTP di Ollama

---

## Docker

### ModalitÃ  senza Blender (solo pipeline LLM)

L'immagine `docker/Dockerfile` esegue esclusivamente le fasi 1-4 della pipeline. Blender non Ã¨ incluso nell'immagine per ragioni di dimensione; il file JSON prodotto deve essere poi utilizzato con un'installazione locale di Blender.

```bash
# Build dell'immagine
make docker-build

# Esecuzione con descrizione come argomento
docker run --rm \
  -v $(pwd)/assets:/app/assets \
  -v $(pwd)/output:/app/output \
  --add-host=host.docker.internal:host-gateway \
  nl2scene3d:latest \
  "una stanza con tavolo e sedia" \
  --output /app/output/scene_objects.json
```

### Docker Compose (pipeline completa + Ollama containerizzato)

Il file `docker-compose.yml` definisce due servizi:

- `ollama`: server Ollama in container con supporto GPU opzionale (NVIDIA)
- `nl2scene3d`: pipeline Python che dipende dal servizio `ollama`

```bash
# Avvia tutti i servizi
make docker-up

# I log di entrambi i servizi
make docker-logs

# Ferma e rimuove i container
make docker-down
```

Il volume `ollama_data` Ã¨ persistente: i modelli scaricati sopravvivono al riavvio dei container e non devono essere riscaricati.

Per abilitare il supporto GPU NVIDIA, verificare che `nvidia-container-toolkit` sia installato sull'host. La configurazione nel `docker-compose.yml` Ã¨ giÃ  predisposta con la sezione `deploy.resources.reservations.devices`.

---

## CI/CD

Il repository include tre workflow GitHub Actions:

### `ci.yml` â€” Integrazione continua

Eseguito su ogni push e pull request verso `main` e `develop`. Comprende tre job paralleli:

- **lint**: esegue `ruff`, `black --check` e `mypy` su Python 3.11 (Ubuntu)
- **test**: esegue pytest con coverage su una matrice di 9 combinazioni (3 OS Ã— 3 versioni Python: 3.10, 3.11, 3.12). Il report di coverage viene caricato su Codecov
- **security**: esegue `bandit` per l'analisi statica della sicurezza e `safety` per il controllo delle dipendenze con vulnerabilitÃ  note

### `docker.yml` â€” Build immagine Docker

Eseguito su push a `main` e su creazione di tag semantici (`v*`). Costruisce l'immagine Docker e la pubblica sul GitHub Container Registry (GHCR) con tag corrispondenti al branch o alla versione.

### Pre-commit hook locali

I seguenti controlli vengono eseguiti localmente prima di ogni commit:

- `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-json`, `check-toml`
- `check-merge-conflict`, `check-added-large-files` (limite 10 MB)
- `debug-statements`, `detect-private-key`
- `black` â€” formattazione
- `ruff` â€” lint con fix automatico
- `mypy` â€” type check con dipendenze di tipo aggiuntive

---

## Risoluzione dei problemi

### Il server Ollama non risponde

```
OllamaConnectionError: Impossibile connettersi a Ollama su http://localhost:11434
```

Verificare che il server sia attivo:

```bash
# Controlla se il processo Ã¨ in esecuzione
ps aux | grep "ollama serve"

# Se non Ã¨ attivo, avviarlo
ollama serve

# Verifica la risposta
curl http://localhost:11434/api/tags
```

Se si utilizza Docker e il container `nl2scene3d` non riesce a raggiungere Ollama sull'host, verificare che `--add-host=host.docker.internal:host-gateway` sia presente nel comando `docker run`, oppure che il servizio `ollama` sia definito in `docker-compose.yml`.

### Il modello restituisce JSON non valido

Il parser implementa tre strategie di estrazione in cascata (parsing diretto, regex, pulizia aggressiva). Se tutte falliscono dopo `max_retries` tentativi, viene sollevata una `RuntimeError`.

Possibili cause e soluzioni:

- **Temperatura troppo alta**: abbassare `temperature` in `config/settings.yaml` (valore raccomandato: 0.1â€“0.2)
- **Modello troppo piccolo**: usare `llama3` o `mistral` invece di modelli da 1-3B parametri
- **Descrizione ambigua**: riformulare la descrizione in modo piÃ¹ esplicito, elencando gli oggetti uno per uno
- **Timeout**: aumentare `OLLAMA_TIMEOUT` nel file `.env` se il modello impiega piÃ¹ di 180 secondi

Per diagnosticare il problema, abilitare il logging di debug:

```bash
python scripts/run_pipeline.py "descrizione" --verbose
```

### Asset non trovato

```
WARNING: Asset 'sofa' non trovato in assets/models. Creo proxy cubo.
```

Il sistema continua l'esecuzione creando un proxy cubo rosso. Per risolvere:

1. Aggiungere il file `assets/models/sofa.obj` (o `.fbx`, `.glb`)
2. Verificare che il nome del file corrisponda esattamente al valore del campo `"name"` nel JSON

### Errori di importazione Pydantic

```
ImportError: cannot import name 'field_validator' from 'pydantic'
```

Il progetto richiede Pydantic v2. Verificare la versione installata:

```bash
python -c "import pydantic; print(pydantic.VERSION)"
pip install "pydantic>=2.5.0"
```

### Blender non trova i moduli del progetto

```
ModuleNotFoundError: No module named 'nl2scene3d'
```

Lo script `blender_runner.py` aggiunge automaticamente `src/` al `sys.path`. Se il problema persiste, verificare che lo script venga eseguito dalla root del repository:

```bash
# Corretto: percorso relativo alla root
blender --background --python scripts/blender_runner.py -- scene_objects.json

# Errato: esecuzione da un'altra directory
cd scripts && blender --background --python blender_runner.py -- ../scene_objects.json
```

---

## Struttura del JSON di output

Il file JSON prodotto dalla pipeline (default: `scene_objects.json`) contiene un array di oggetti con la seguente struttura:

```json
[
  {
    "name": "table",
    "x": 0.0,
    "y": 0.0,
    "z": 0.0,
    "rot_x": 0.0,
    "rot_y": 0.0,
    "rot_z": 0.0,
    "scale": 1.0
  },
  {
    "name": "chair",
    "x": 0.0,
    "y": -1.2,
    "z": 0.0,
    "rot_x": 0.0,
    "rot_y": 0.0,
    "rot_z": 0.0,
    "scale": 1.0
  }
]
```

| Campo | Tipo | Descrizione |
|---|---|---|
| `name` | string | Nome dell'oggetto in inglese minuscolo, corrisponde al nome del file asset |
| `x` | float | Posizione sull'asse X in unitÃ  Blender (1 unitÃ  = 1 metro) |
| `y` | float | Posizione sull'asse Y in unitÃ  Blender |
| `z` | float | Posizione sull'asse Z (0.0 = livello del pavimento) |
| `rot_x` | float | Rotazione attorno all'asse X in radianti |
| `rot_y` | float | Rotazione attorno all'asse Y in radianti |
| `rot_z` | float | Rotazione attorno all'asse Z in radianti |
| `scale` | float | Fattore di scala uniforme (1.0 = dimensioni originali dell'asset) |

Il file JSON puÃ² essere modificato manualmente prima di passarlo a Blender per aggiustamenti fini del layout.

---

## Licenza

Questo progetto Ã¨ distribuito sotto licenza MIT. Consultare il file [LICENSE](LICENSE) per il testo completo.
