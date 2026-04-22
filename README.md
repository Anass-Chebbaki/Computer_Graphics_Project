
# NL2Scene3D — Natural Language to 3D Scene Generator

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![CI](https://github.com/Anass-Chebbaki/Computer_Graphics_Project/actions/workflows/ci.yml/badge.svg)](https://github.com/Anass-Chebbaki/Computer_Graphics_Project/actions/workflows/ci.yml)

NL2Scene3D è una pipeline automatizzata che converte descrizioni testuali in linguaggio naturale in scene 3D complete all'interno di Blender. Il sistema utilizza modelli linguistici di grandi dimensioni (LLM) eseguiti localmente tramite Ollama per interpretare la descrizione dell'utente, generare un layout spaziale strutturato in formato JSON e applicarlo programmaticamente a una scena Blender tramite l'API `bpy`.

Il progetto è progettato per funzionare interamente in locale, senza dipendenze da servizi cloud o API esterne a pagamento.

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

La pipeline è composta da sei fasi sequenziali, ciascuna implementata in un modulo dedicato:

```
Descrizione testuale (linguaggio naturale)
          │
          ▼
  [1] InputHandler
      Normalizzazione e validazione del testo di input.
      Supporta input da stringa, terminale interattivo o file .txt.
          │
          ▼
  [2] PromptBuilder
      Costruzione del prompt di sistema e del payload per Ollama.
      Il prompt vincola il modello a rispondere esclusivamente
      con un array JSON strutturato secondo uno schema fisso.
          │
          ▼
  [3] OllamaClient
      Chiamata HTTP POST all'endpoint /api/chat del server Ollama locale.
      Gestisce timeout, retry su errori di rete e health check preliminare.
          │
          ▼
  [4] JSONParser + Validator
      Estrazione robusta del JSON dalla risposta del modello
      (parsing diretto, regex, pulizia aggressiva di markdown e commenti).
      Validazione di ogni oggetto con Pydantic e coercizione dei tipi.
      ┌─────────────────────────────────────────────────┐
      │  Supporta oggetti della scena con:              │
      │  • Gerarchia parent-child per raggruppamenti    │
      │  • Semantica materiali procedurali (wood, glass │
      │    fabric, metal, plastic, concrete, ecc.)      │
      │  • Sorgenti luminose (point, sun, spot, area)   │
      │    con colori RGB, intensità e angoli spot      │
      └─────────────────────────────────────────────────┘
          │
          ▼
  [4.5] SceneGraph
      Sistema di layout spaziale basato su bounding box orientati (OBB).
      Calcola le intersezioni tra oggetti ruotati e risolve le sovrapposizioni
      spostando gli elementi lungo la direzione centro-centro.
      In caso di conflitti persistenti, fornisce feedback al modello
      per la rigenerazione delle coordinate.
          │
          ▼
  [5] SceneBuilder + Renderer (Blender / bpy)
      Configurazione di luci, camera e ambiente (HDRI).
      Importazione degli asset con allineamento alle superfici tramite raycasting.
      Applicazione di materiali PBR (configurabili via YAML o texture locali).
      Esportazione in formati 2D (PNG) e 3D (GLB, USDZ).
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
    "scale": 1.0,
    "parent": null,
    "material_semantics": "wood"
  },
  {
    "name": "lamp",
    "x": 2.0,
    "y": 0.0,
    "z": 0.0,
    "scale": 1.0,
    "light_type": "POINT",
    "color": [1.0, 1.0, 0.85],
    "energy": 2000.0
  }
]
```

Tutte le coordinate sono espresse in unità Blender (1 unità = 1 metro). Le rotazioni sono in radianti nel sistema Euler XYZ. I colori RGB sono normalizzati all'intervallo `[0.0, 1.0]`.

---

## Struttura del repository

```
Computer_Graphics_Project/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                 # Lint, test, security su push/PR
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
│       ├── system_prompt.txt      # Prompt di sistema per il modello LLM
│       └── multi_room_prompt.txt  # Prompt avanzato per scene multi-stanza
├── docs/
│   ├── architecture.md            # Documentazione architettura dettagliata
│   ├── installation.md            # Guida all'installazione
│   ├── usage.md                   # Guida all'utilizzo
│   └── contributing.md            # Guida alla contribuzione
├── src/
│   └── computer_graphics/
│       ├── __init__.py
│       ├── cli.py                 # Entry point CLI (computer-graphics)
│       ├── config_loader.py       # Caricamento config YAML + .env
│       ├── input_handler.py       # Fase 1: gestione input utente
│       ├── prompt_builder.py      # Fase 2: costruzione payload Ollama
│       ├── ollama_client.py       # Fase 3: client HTTP per Ollama
│       ├── json_parser.py         # Fase 4: parsing robusto del JSON
│       ├── validator.py           # Fase 4: validazione con Pydantic
│       │                          #        Supporta SceneObject, LightObject
│       │                          #        Gerarchia parent-child, materiali
│       ├── scene_graph.py         # Fase 4.5: layout spaziale e collisioni
│       ├── orchestrator.py        # Coordinamento con ciclo agentico retry
│       └── blender/
│           ├── __init__.py
│           ├── scene_builder.py   # Costruzione scena, importazione asset,
│           │                      # snap alle superfici, materiali PBR
│           └── renderer.py        # Rendering PNG ed esportazione GLB/USDZ
├── scripts/
│   ├── run_pipeline.py            # Entry point CLI principale
│   ├── blender_runner.py          # Script da eseguire dentro Blender
│   ├── generate_primitives.py     # Generatore automatico asset 3D primitivi
│   └── setup_assets.py            # Utility per la libreria asset
├── tests/
│   ├── conftest.py                # Fixture condivise
│   ├── test_input_handler.py
│   ├── test_prompt_builder.py
│   ├── test_ollama_client.py
│   ├── test_json_parser.py
│   ├── test_validator.py
│   ├── test_scene_graph.py
│   ├── test_orchestrator.py
│   └── fixtures/
│       ├── sample_response_clean.json
│       ├── sample_response_dirty.txt
│       └── sample_objects.json
├── docker/
│   ├── Dockerfile
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
| Docker | 24.0 | Opzionale, necessario solo per la modalità containerizzata |
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
| `bandit` | >=1.7.0 | Analisi statica della sicurezza |
| `pip-audit` | >=2.6.0 | Verifica vulnerabilità nelle dipendenze |

---

## Installazione

### Installazione di Ollama

Ollama è l'unico componente che richiede installazione separata. Espone un server HTTP locale sulla porta 11434 che riceve le richieste di inferenza.

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

Il server risponde sulla porta `11434`. Questa è anche la porta configurata di default in `config/settings.yaml` e nel file `.env.example`.

Modelli alternativi supportati (con compromessi velocità/qualità):

| Modello | Dimensione | Qualità JSON | Note |
|---|---|---|---|
| `llama3` / `llama3:8b` | ~4 GB | ★★★★☆ | Raccomandato, buon bilanciamento |
| `mistral` | ~4 GB | ★★★★☆ | Alternativa valida |
| `phi3` | ~2 GB | ★★★☆☆ | Leggero, adatto a macchine con poca RAM |
| `llama3:70b` | ~40 GB | ★★★★★ | Alta qualità, richiede hardware dedicato |

### Installazione del progetto

```bash
# Clona il repository
git clone https://github.com/yourusername/Computer_Graphics_Project.git
cd Computer_Graphics_Project

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
# Verifica tutti i prerequisiti di sistema in un colpo solo
computer-graphics check

# Esegui la suite di test
make test

# Verifica che Ollama sia raggiungibile
python -c "from computer_graphics.ollama_client import OllamaClient; print(OllamaClient().health_check())"
```

### Generazione asset primitivi

Se non si dispone di modelli 3D, è possibile generare automaticamente asset primitivi con Blender. Lo script `scripts/generate_primitives.py` costruisce geometria di base (tavolo con piano e gambe, sedia con sedile e schienale, lampada con base e paralume, ecc.) ed esporta ogni oggetto come file `.obj` nella directory `assets/models/`.

```bash
make generate-primitives
```

Questo consente di dimostrare la pipeline completa — dall'input testuale al render finale — senza dipendere da asset esterni.

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

Le variabili d'ambiente hanno sempre la precedenza sulle impostazioni definite in `config/settings.yaml`. Il caricamento segue questa priorità: **variabili d'ambiente → file `.env` → `settings.yaml` → valori di default**.

### File `config/settings.yaml`

Il file YAML centralizza tutti i parametri di configurazione:

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

Il prompt di sistema in `config/prompts/system_prompt.txt` è il componente più critico per la qualità dell'output. Istruisce il modello a rispondere esclusivamente con un array JSON valido secondo lo schema atteso. Il file può essere modificato per adattare il comportamento del modello senza toccare il codice sorgente.

Per scene complesse con molti oggetti o layout multi-stanza, è disponibile il prompt alternativo `config/prompts/multi_room_prompt.txt`, che include linee guida spaziali più dettagliate e vincoli di distanza tra zone funzionali.

Il `PromptBuilder` carica il prompt con questa priorità:
1. Testo passato esplicitamente come argomento al costruttore
2. File specificato tramite il parametro `system_prompt_file`
3. File nel percorso convenzionale `config/prompts/system_prompt.txt`
4. Prompt di default hardcoded nel modulo `prompt_builder.py`

---

## Utilizzo

### Esecuzione rapida

```bash
# Demo con descrizione predefinita (non richiede input interattivo)
make demo

# Modalità interattiva: chiede la descrizione a terminale
make pipeline

# Costruzione scena in Blender senza render
make blender-run

# Costruzione scena in Blender con render PNG
make blender-render

# Genera asset 3D primitivi (.obj) per tutti gli oggetti supportati
make generate-primitives

# Verifica lo stato della libreria di asset
make check-assets
```

### CLI installata (`computer-graphics`)

Dopo `pip install -e .`, il comando `computer-graphics` è disponibile globalmente:

```bash
# Descrizione come argomento
computer-graphics generate "una cucina con tavolo, due sedie e un frigorifero"

# Modalità interattiva
computer-graphics generate --interactive

# Da file di testo
computer-graphics generate --file descrizione.txt

# Con lancio automatico di Blender al termine della pipeline
computer-graphics generate "una stanza con tavolo e sedia" --blender

# Con lancio automatico di Blender e render PNG
computer-graphics generate "una stanza con tavolo e sedia" --blender --render

# Specifica modello, output e numero di tentativi
computer-graphics generate "scrivania con monitor" \
  --model mistral \
  --output scrivania.json \
  --retries 5

# Modalità verbose per debug
computer-graphics generate "test" --verbose

# Verifica prerequisiti di sistema (Ollama, Blender, Python, asset)
computer-graphics check

# Mostra la configurazione corrente
computer-graphics info

# Valida un file JSON di oggetti esistente
computer-graphics validate scene_objects.json
```

### Script `run_pipeline.py`

Lo script gestisce le fasi 1–4.5 (input → JSON con layout anti-collisione) e salva il risultato in un file JSON:

```bash
# Descrizione passata come argomento
python scripts/run_pipeline.py "una cucina con tavolo, due sedie e un frigorifero"

# Modalità interattiva
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
```

### Script `blender_runner.py`

Lo script gestisce la fase 5 (JSON → scena 3D) ed è progettato per essere eseguito dentro Blender:

```bash
# Costruzione scena in Blender dal JSON generato
blender --background --python scripts/blender_runner.py -- scene_objects.json

# Costruzione scena con render PNG
blender --background --python scripts/blender_runner.py \
  -- scene_objects.json \
  --render assets/renders/output.png

# Solo costruzione scena, senza render
blender --background --python scripts/blender_runner.py \
  -- scene_objects.json \
  --no-render
```

### Utilizzo come libreria Python

```python
from computer_graphics.orchestrator import generate_scene_objects
from computer_graphics.scene_graph import apply_scene_graph
from computer_graphics.ollama_client import OllamaClient

# Verifica che Ollama sia raggiungibile
client = OllamaClient()
if not client.health_check():
    raise RuntimeError("Ollama non è raggiungibile. Eseguire: ollama serve")

# Esecuzione della pipeline (include layout anti-collisione)
objects = generate_scene_objects(
    scene_description="una stanza con tavolo, sedia e lampada da terra",
    model="llama3",
    max_retries=3,
    ollama_url="http://localhost:11434",
    timeout=180,
    verbose=True,
)

# Ogni oggetto è un'istanza Pydantic con accesso diretto agli attributi
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

## Oggetti e funzionalità avanzate

### Gerarchia parent-child

Gli oggetti della scena supportano una gerarchia gerarchica tramite il campo `parent`. Questo consente di creare raggruppamenti logici dove le coordinate dei figli sono relative al padre:

```json
[
  {
    "name": "desk",
    "x": 0.0,
    "y": 0.0,
    "z": 0.0,
    "scale": 1.6
  },
  {
    "name": "monitor",
    "x": 0.3,
    "y": 0.1,
    "z": 0.75,
    "scale": 0.8,
    "parent": "desk"
  },
  {
    "name": "keyboard",
    "x": 0.0,
    "y": 0.3,
    "z": 0.05,
    "scale": 1.0,
    "parent": "desk"
  }
]
```

In Blender, il mondo `SceneBuilder` crea automaticamente vincoli genitore-figlio (`parent_set()`) e applica le trasformazioni relative.

### Sorgenti luminose

Il modello può generare sorgenti luminose oltre ai soli oggetti. Ogni sorgente è rappresentata da un oggetto `LightObject` con:

- **Tipo di luce**: `POINT` (omni-direzionale), `SUN` (direzionale infinita), `SPOT` (cono focalizzato), `AREA` (emissione di superficie)
- **Colore RGB**: Tripla normalizzata `[0.0, 1.0]` per canale (es. bianco `[1.0, 1.0, 1.0]`, giallo lampato `[1.0, 1.0, 0.8]`)
- **Intensità**: `energy` in Watt (Cycles render) o unità arbitrarie (EEVEE)
- **Angolo spot** (solo SPOT): `spot_size` in radianti (~0.785 rad ≈ 45°)

Esempio:

```json
{
  "name": "overhead_light",
  "light_type": "SUN",
  "x": 0.0,
  "y": 0.0,
  "z": 10.0,
  "color": [1.0, 0.95, 0.8],
  "energy": 3000.0
}
```

### Materiali procedurali

Il campo `material_semantics` permette al modello di specificare il tipo di materiale in modo dichiarativo. `SceneBuilder` applica shader procedurali corrispondenti:

| Semantica | Descrizione | Proprietà | Shader |
|---|---|---|---|
| `wood` | Legno | Diffuso marrone, bump, venatura | Procedurale legno |
| `glass` | Vetro trasparente | IOR 1.45, traslucenza | Glass BSDF |
| `fabric` | Tessuto morbido | Diffuso satinato, micro-roughness | Diffuse + Coat |
| `metal` | Metallo lucido | Specular alto, IOR metallico | Metal BSDF |
| `plastic` | Plastica | Diffuso leggero, specular medio | Diffuse + Glossy |
| `concrete` | Cemento | Diffuso grigio, roughness alta, pori | Procedurale |
| `ceramic` | Ceramica | Glittery, specular sottile | Glossy + Diffuse |
| `leather` | Pelle | Marrone scuro, anisotropic | Anisotropic |
| `marble` | Marmo | Bianco, venature fini, specular | Procedurale |
| `rubber` | Gomma | Nero opaco, roughness alta | Matte |

### Configurazione Materiali PBR

I parametri degli shader (metallic, roughness, IOR, ecc.) sono definiti in `config/materials.yaml`. Il sistema supporta l'applicazione automatica di texture PBR se presenti nella struttura:

`assets/textures/<material_semantics>/[albedo|roughness|normal|displacement].[png|jpg]`

### Allineamento alle superfici (Surface Snap)

Il sistema utilizza algoritmi di raycasting per rilevare le superfici sottostanti agli oggetti (pavimenti, ripiani, ecc.) e corregge automaticamente la coordinata Z per garantire il contatto fisico, evitando oggetti sospesi o compenetrati nelle basi.

Esempio:

```json
[
  {
    "name": "table",
    "material_semantics": "wood",
    "scale": 2.0
  },
  {
    "name": "glass_vase",
    "material_semantics": "glass",
    "scale": 0.5
  }
]
```

### Risoluzione automatica delle collisioni

La fase **SceneGraph** rileva automaticamente le sovrapposizioni tra bounding box AABB e applica iterazioni di aggiustamento coordinato per risolverle. Se le collisioni non sono risolvibili spazialmente (troppi oggetti in uno spazio ristretto), viene attivato un **ciclo agentico**:

1. **Rilevamento**: SceneGraph calcola la densità della scena (oggetti / metri quadri)
2. **Analisi**: Se la densità supera una soglia e rimangono collisioni, identifica la coppia più problematica
3. **Feedback**: Genera un messaggio con istruzioni esplicite per il modello: *"Aumenta la distanza tra `object_a` e `object_b` di almeno 1.5 metri"*
4. **Regenerazione**: Reinvia il feedback al modello tramite il ciclo di conversazione, chiedendo di rigenerare le coordinate
5. **Iterazione**: Ripete fino a 3 tentativi (configurabile con `--retries`)

Questo garantisce che anche scene complesse convergano verso un layout fisicamente valido senza richiedere manuale post-processing dei risultati.

---

## Riferimento CLI

### `computer-graphics generate`

```
Utilizzo: computer-graphics generate [OPZIONI] [DESCRIZIONE]

Argomenti:
  DESCRIZIONE           Testo della scena da generare

Opzioni:
  -i, --interactive     Chiede la descrizione interattivamente a terminale
  -f, --file PATH       Legge la descrizione da un file .txt
  -m, --model TEXT      Nome del modello Ollama da usare  [default: da settings.yaml]
  -o, --output PATH     File JSON di output  [default: scene_objects.json]
  -r, --retries INT     Numero massimo di tentativi  [default: 3]
  --ollama-url TEXT     URL del server Ollama  [default: http://localhost:11434]
  -v, --verbose         Output di debug dettagliato
  -b, --blender         Lancia automaticamente Blender al termine
  --render              Genera il render PNG (richiede --blender)
  --render-output PATH  Percorso output PNG  [default: assets/renders/output.png]
  --export-glb          Esporta la scena in formato .glb
  --export-usdz         Esporta la scena in formato .usdz
  --export-output PATH  Percorso base per l'export 3D
  --help                Mostra questo messaggio ed esce
```

### `python scripts/run_pipeline.py`

```
Utilizzo: python scripts/run_pipeline.py [OPZIONI] [DESCRIZIONE]

Opzioni:
  -i, --interactive     Chiede la descrizione interattivamente a terminale
  -f, --file PATH       Legge la descrizione da un file .txt
  -m, --model TEXT      Nome del modello Ollama  [default: llama3]
  -o, --output PATH     File JSON di output  [default: scene_objects.json]
  -r, --retries INT     Numero massimo di tentativi  [default: 3]
  --ollama-url TEXT     URL del server Ollama  [default: http://localhost:11434]
  -v, --verbose         Output di debug dettagliato
  --help                Mostra questo messaggio ed esce
```

### `blender --background --python scripts/blender_runner.py`

```
Utilizzo: blender --background --python scripts/blender_runner.py -- [OPZIONI] JSON_PATH

Argomenti posizionali:
  JSON_PATH             Percorso al file JSON generato dalla pipeline

Opzioni:
  --render PATH         Abilita il render e salva il PNG nel percorso specificato
  --no-render           Disabilita il render (costruisce solo la scena)
```

### Comandi Makefile

```
install              Installa le dipendenze di produzione
install-dev          Installa tutte le dipendenze, incluse quelle di sviluppo
lint                 Esegue ruff linter su src/, tests/, scripts/
format               Formatta il codice con black e ruff --fix
type-check           Controllo statico dei tipi con mypy
test                 Esegue la suite di test con pytest
test-cov             Esegue i test con report di coverage HTML in htmlcov/
coverage-open        Apre il report coverage nel browser
ollama-start         Avvia il server Ollama in background
ollama-pull          Scarica il modello specificato (default: llama3)
ollama-status        Mostra i modelli disponibili nel server locale
pipeline             Esegue la pipeline in modalità interattiva
demo                 Esecuzione rapida con descrizione hardcoded di esempio
blender-run          Avvia Blender con lo script di costruzione scena
blender-render       Avvia Blender con costruzione scena e render PNG
generate-primitives  Genera asset 3D primitivi con Blender
check-assets         Verifica lo stato della libreria di asset
asset-report         Genera report JSON degli asset
cli-check            Verifica prerequisiti via CLI
cli-info             Mostra configurazione via CLI
cli-demo             Demo completa via comando computer-graphics
cli-validate         Valida il JSON di output corrente
docker-build         Costruisce l'immagine Docker
docker-up            Avvia tutti i servizi con Docker Compose
docker-down          Ferma i servizi Docker
docker-logs          Mostra i log dei container in tempo reale
clean                Rimuove file temporanei, cache e artefatti di build
```

---

## Asset 3D

La directory `assets/models/` deve contenere i modelli 3D da importare nella scena. Il sistema cerca i file con il nome corrispondente all'oggetto generato dal modello LLM nei formati seguenti, in ordine di priorità:

1. `.obj` (Wavefront OBJ)
2. `.fbx` (Autodesk FBX)
3. `.glb` / `.gltf` (GL Transmission Format)

Il nome del file deve corrispondere esattamente al nome in inglese che il modello LLM restituisce nel campo `"name"` del JSON. Ad esempio, se il modello genera `"name": "table"`, il sistema cerca `assets/models/table.obj`.

| File asset | Oggetto | Dimensioni approssimative |
|---|---|---|
| `table.obj` | Tavolo | 1.5 × 0.9 × 0.75 m |
| `chair.obj` | Sedia | 0.6 × 0.6 × 1.0 m |
| `lamp.obj` | Lampada da terra | 0.4 × 0.4 × 1.8 m |
| `desk.obj` | Scrivania | 1.6 × 0.8 × 0.75 m |
| `sofa.obj` | Divano | 2.2 × 0.9 × 0.9 m |
| `bookshelf.obj` | Libreria | 0.9 × 0.3 × 1.8 m |
| `monitor.obj` | Monitor | 0.6 × 0.2 × 0.4 m |
| `bed.obj` | Letto | 1.6 × 2.0 × 0.6 m |
| `plant.obj` | Pianta in vaso | 0.5 × 0.5 × 1.0 m |
| `cabinet.obj` | Armadio | 0.8 × 0.4 × 1.4 m |
| `fridge.obj` | Frigorifero | 0.7 × 0.7 × 1.8 m |
| `rug.obj` | Tappeto | 2.0 × 1.5 × 0.02 m |

Se un asset non viene trovato, il sistema crea automaticamente un cubo proxy con materiale rosso semitrasparente e lo posiziona nelle coordinate previste. Questo comportamento permette di verificare il layout spaziale anche prima di disporre di tutti gli asset definitivi.

Le dimensioni approssimative di ogni oggetto sono utilizzate dal modulo `scene_graph.py` per il calcolo dei bounding box e la risoluzione delle collisioni.

### Fonti gratuite

- [Poly Haven](https://polyhaven.com) — modelli in formato `.glb`, licenza CC0
- [Sketchfab](https://sketchfab.com/features/free-3d-models) — vari formati, licenze miste
- [BlendSwap](https://www.blendswap.com) — modelli nativi Blender
- [OpenGameArt](https://opengameart.org) — modelli in formati aperti, licenze libere

I file binari degli asset non sono inclusi nel repository. Per repository con modelli di grandi dimensioni, si consiglia di utilizzare [Git LFS](https://git-lfs.com).

### Verifica e report della libreria

```bash
# Verifica quali asset sono presenti e quali mancano
python scripts/setup_assets.py check

# Genera un report JSON completo con dimensioni e fonti suggerite
python scripts/setup_assets.py report --output asset_report.json
```

---

## Sviluppo

### Workflow consigliato

```bash
# Attiva l'ambiente virtuale
source .venv/bin/activate

# Installa le dipendenze di sviluppo (se non già fatto)
make install-dev

# Installa i pre-commit hook
pre-commit install

# Ciclo di sviluppo standard
make lint          # Controlla lo stile del codice
make format        # Applica formattazione automatica
make type-check    # Controlla la correttezza dei tipi
make test          # Esegue i test
make test-cov      # Esegue i test con report di coverage
```

### Convenzioni di codice

Il progetto adotta le seguenti convenzioni:

- **Formattatore**: `black` con lunghezza riga massima di 88 caratteri
- **Linter**: `ruff` con i ruleset `E`, `F`, `W`, `I`, `N`, `UP`, `ANN`, `B`, `C4`, `SIM`
- **Type checking**: `mypy` in modalità strict per i moduli interni
- **Docstring**: stile Google per tutti i metodi pubblici
- **Annotazioni di tipo**: obbligatorie per tutte le funzioni pubbliche
- **Import**: ordinati con `isort` (integrato in ruff con ruleset `I`)
- **Commit**: formato [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `test:`, ecc.)

I pre-commit hook verificano automaticamente queste convenzioni prima di ogni commit. Per eseguire i controlli manualmente su tutti i file:

```bash
pre-commit run --all-files
```

### Struttura dei moduli

Ogni modulo corrisponde a una fase precisa della pipeline.

I moduli nella directory `src/computer_graphics/blender/` dipendono da `bpy` e possono essere importati solo all'interno del processo Blender. Non importarli in contesti Python standard: causeranno un `ImportError`.

Il modulo `orchestrator.py` è il punto di coordinamento principale. Istanzia i componenti delle fasi 1–4.5, gestisce la logica di retry e produce la lista finale di `SceneObject` validati e posizionati senza collisioni. È il punto di ingresso raccomandato per l'utilizzo programmatico della pipeline.

Il modulo `scene_graph.py` implementa un sistema di layout spaziale con bounding box AABB (Axis-Aligned Bounding Box). Gli oggetti più grandi mantengono la posizione originale generata dal modello; gli oggetti più piccoli vengono spostati lungo la direzione di minima penetrazione in caso di sovrapposizione. Il sistema itera fino a convergenza o fino al numero massimo di iterazioni configurato.

Il modulo `config_loader.py` gestisce il caricamento della configurazione con fusione a priorità da `.env`, `settings.yaml` e valori di default. Espone un'interfaccia semplice tramite `ConfigLoader.load()` e `ConfigLoader.get("sezione", "chiave")`.

### Aggiungere un nuovo tipo di oggetto

Per aggiungere il supporto a un nuovo asset (es. `"wardrobe"`):

1. Aggiungere il nome in `KNOWN_ASSET_NAMES` in `src/computer_graphics/validator.py`
2. Aggiungere le dimensioni reali in `OBJECT_DIMENSIONS` in `src/computer_graphics/scene_graph.py`
3. Aggiungere la definizione geometrica in `ASSET_DEFINITIONS` in `scripts/generate_primitives.py`
4. Aggiungere `wardrobe.obj` (o generarlo con `make generate-primitives`) in `assets/models/`

---

## Test

### Esecuzione

```bash
# Suite completa
make test

# Con report di coverage a terminale e HTML
make test-cov

# Apre il report HTML nel browser
make coverage-open

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
| `test_input_handler.py` | `input_handler.py` | Validazione, factory method, mock interattivo |
| `test_prompt_builder.py` | `prompt_builder.py` | Struttura payload, caricamento prompt da file |
| `test_ollama_client.py` | `ollama_client.py` | Mock HTTP con `responses`, health check |
| `test_json_parser.py` | `json_parser.py` | Input puliti e sporchi, casi limite |
| `test_validator.py` | `validator.py` | Validazione Pydantic, coercizione tipi |
| `test_scene_graph.py` | `scene_graph.py` | AABB, rilevamento e risoluzione collisioni |
| `test_orchestrator.py` | `orchestrator.py` | Test di integrazione con mock, logica retry |

I moduli che dipendono da `bpy` (fase 5) non sono inclusi nella suite di test standard, poiché richiedono un processo Blender attivo. Devono essere testati manualmente o tramite uno script di smoke test eseguito all'interno di Blender.

### Fixture

Le fixture condivise sono definite in `tests/conftest.py` e includono:

- `sample_clean_json`: output JSON ideale del modello, pronto per il parsing
- `sample_dirty_text`: testo con backtick markdown, commenti JavaScript e virgole finali (caso reale frequente)
- `valid_objects_list`: lista di dizionari già normalizzati per i test del validator
- `mock_ollama_response`: struttura JSON simulata della risposta HTTP di Ollama

I file in `tests/fixtures/` contengono esempi reali di output del modello usati nei test parametrizzati.

---

## Docker

### Modalità senza Blender (solo pipeline LLM)

L'immagine `docker/Dockerfile` esegue esclusivamente le fasi 1–4.5 della pipeline. Blender non è incluso nell'immagine per ragioni di dimensione; il file JSON prodotto deve essere poi utilizzato con un'installazione locale di Blender.

```bash
# Build dell'immagine
make docker-build

# Esecuzione con descrizione come argomento
docker run --rm \
  -v $(pwd)/assets:/app/assets \
  -v $(pwd)/output:/app/output \
  --add-host=host.docker.internal:host-gateway \
  computer-graphics:latest \
  "una stanza con tavolo e sedia" \
  --output /app/output/scene_objects.json
```

### Docker Compose (pipeline completa + Ollama containerizzato)

Il file `docker-compose.yml` definisce due servizi:

- `ollama`: server Ollama in container con supporto GPU opzionale (NVIDIA)
- `computer-graphics`: pipeline Python che dipende dal servizio `ollama`

```bash
# Avvia tutti i servizi
make docker-up

# Log di entrambi i servizi in tempo reale
make docker-logs

# Ferma e rimuove i container
make docker-down
```

Il volume `ollama_data` è persistente: i modelli scaricati sopravvivono al riavvio dei container e non devono essere riscaricati.

L'`entrypoint.sh` attende automaticamente che Ollama sia pronto prima di avviare la pipeline, scarica il modello se non è già disponibile nel volume, e gestisce gli errori in modo pulito.

Per abilitare il supporto GPU NVIDIA, verificare che `nvidia-container-toolkit` sia installato sull'host. La configurazione nel `docker-compose.yml` è già predisposta con la sezione `deploy.resources.reservations.devices`.

---

## CI/CD

Il repository include workflow GitHub Actions per integrazione continua e distribuzione.

### `ci.yml` — Integrazione continua

Eseguito su ogni push e pull request verso `main` e `develop`. Comprende quattro job paralleli:

- **lint**: esegue `ruff`, `black --check` e `mypy` su Python 3.11 (Ubuntu)
- **test**: esegue pytest con coverage su una matrice di 9 combinazioni (3 OS × 3 versioni Python: 3.10, 3.11, 3.12). Il report di coverage viene caricato su Codecov
- **security**: esegue `bandit` per l'analisi statica della sicurezza e `pip-audit` per il controllo delle dipendenze con vulnerabilità note
- **coverage-report**: gate di coverage con soglia minima configurata; blocca il merge se la copertura scende sotto la soglia

Il workflow utilizza `concurrency` con `cancel-in-progress: true` per evitare run ridondanti sullo stesso branch.

### `docker.yml` — Build immagine Docker

Eseguito su push a `main` e su creazione di tag semantici (`v*`). Costruisce l'immagine Docker e la pubblica sul GitHub Container Registry (GHCR) con tag corrispondenti al branch o alla versione.

### Pre-commit hook locali

I seguenti controlli vengono eseguiti localmente prima di ogni commit:

- `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-json`, `check-toml`
- `check-merge-conflict`, `check-added-large-files` (limite 10 MB)
- `debug-statements`, `detect-private-key`
- `black` — formattazione
- `ruff` — lint con fix automatico
- `mypy` — type check con dipendenze di tipo aggiuntive

---

## Risoluzione dei problemi

### Il server Ollama non risponde

```
OllamaConnectionError: Impossibile connettersi a Ollama su http://localhost:11434
```

Verificare che il server sia attivo:

```bash
# Controlla se il processo è in esecuzione
ps aux | grep "ollama serve"

# Se non è attivo, avviarlo
ollama serve

# Verifica la risposta
curl http://localhost:11434/api/tags
```

In alternativa, usare il comando integrato per la diagnostica completa:

```bash
computer-graphics check
```

Se si utilizza Docker e il container non riesce a raggiungere Ollama sull'host, verificare che `--add-host=host.docker.internal:host-gateway` sia presente nel comando `docker run`, oppure che il servizio `ollama` sia definito in `docker-compose.yml`.

### Il modello restituisce JSON non valido

Il parser implementa tre strategie di estrazione in cascata (parsing diretto, regex, pulizia aggressiva). Se tutte falliscono dopo `max_retries` tentativi, viene sollevata una `RuntimeError`.

Possibili cause e soluzioni:

- **Temperatura troppo alta**: abbassare `temperature` in `config/settings.yaml` (valore raccomandato: 0.1–0.2)
- **Modello troppo piccolo**: usare `llama3` o `mistral` invece di modelli da 1–3B parametri
- **Descrizione ambigua**: riformulare la descrizione in modo più esplicito, elencando gli oggetti uno per uno
- **Timeout**: aumentare `OLLAMA_TIMEOUT` nel file `.env` se il modello impiega più di 180 secondi

Per diagnosticare il problema, abilitare il logging di debug:

```bash
python scripts/run_pipeline.py "descrizione" --verbose
# oppure
computer-graphics generate "descrizione" --verbose
```

### Asset non trovato

```
WARNING: Asset 'sofa' non trovato in assets/models. Creo proxy cubo.
```

Il sistema continua l'esecuzione creando un cubo proxy rosso semitrasparente. Per risolvere:

1. Aggiungere il file `assets/models/sofa.obj` (o `.fbx`, `.glb`)
2. Oppure eseguire `make generate-primitives` per generare un asset primitivo
3. Verificare che il nome del file corrisponda esattamente al valore del campo `"name"` nel JSON

```bash
# Visualizza un report completo degli asset presenti e mancanti
make check-assets
```

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
ModuleNotFoundError: No module named 'computer_graphics'
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
| `x` | float | Posizione sull'asse X in unità Blender (1 unità = 1 metro) |
| `y` | float | Posizione sull'asse Y in unità Blender |
| `z` | float | Posizione sull'asse Z (0.0 = livello del pavimento) |
| `rot_x` | float | Rotazione attorno all'asse X in radianti |
| `rot_y` | float | Rotazione attorno all'asse Y in radianti |
| `rot_z` | float | Rotazione attorno all'asse Z in radianti |
| `scale` | float | Fattore di scala uniforme (1.0 = dimensioni originali dell'asset) |

Il file JSON può essere modificato manualmente prima di passarlo a Blender per aggiustamenti fini del layout. Può essere validato con:

```bash
computer-graphics validate scene_objects.json
```

---

## Licenza

Questo progetto è distribuito sotto licenza MIT. Consultare il file [LICENSE](LICENSE) per il testo completo.
