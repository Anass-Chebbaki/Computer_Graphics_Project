# NL2Scene3D — Natural Language to 3D Scene Generator

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![CI](https://github.com/Anass-Chebbaki/Computer_Graphics_Project/actions/workflows/ci.yml/badge.svg)](https://github.com/Anass-Chebbaki/Computer_Graphics_Project/actions/workflows/ci.yml)

NL2Scene3D is an automated pipeline that converts natural language text descriptions into complete 3D scenes inside Blender. The system uses large language models (LLMs) running locally via Ollama to interpret the user's description, generate a structured spatial layout in JSON format, and apply it programmatically to a Blender scene via the `bpy` API.

The project is designed to run entirely offline, with no dependencies on cloud services or paid external APIs.

---

## Table of Contents

- [Pipeline Architecture](#pipeline-architecture)
- [Repository Structure](#repository-structure)
- [System Requirements](#system-requirements)
- [Quick Start Guide](#quick-start-guide)
- [Dependencies](#dependencies)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [CLI Reference](#cli-reference)
- [Advanced Features](#advanced-features)
- [3D Assets](#3d-assets)
- [Development](#development)
- [Testing](#testing)
- [Docker](#docker)
- [CI/CD](#cicd)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Pipeline Architecture

The pipeline consists of six sequential stages, each implemented in a dedicated module:

```
Natural language text description
          │
          ▼
  [1] InputHandler
      Normalization and validation of the input text.
      Supports input from a string, interactive terminal, or .txt file.
          │
          ▼
  [2] PromptBuilder
      Construction of the system prompt and Ollama payload.
      The prompt constrains the model to respond exclusively
      with a structured JSON array conforming to a fixed schema.
          │
          ▼
  [3] OllamaClient
      HTTP POST request to the /api/chat endpoint of the local Ollama server.
      Handles timeouts, network-error retries, and preliminary health checks.
          │
          ▼
  [4] JSONParser + Validator
      JSON extraction from the model response via bracket balancing.
      Per-object validation with Pydantic and type coercion.
      ┌─────────────────────────────────────────────────┐
      │  Scene objects support:                         │
      │  • Parent-child hierarchy for groupings         │
      │  • Procedural material semantics (wood, glass,  │
      │    fabric, metal, plastic, concrete, etc.)      │
      │  • Light sources (point, sun, spot, area)       │
      │    with RGB colors, intensity, and spot angles  │
      └─────────────────────────────────────────────────┘
          │
          ▼
  [4.5] SceneGraph
      Spatial layout system based on oriented bounding boxes (OBB).
      Computes intersections between rotated objects and resolves overlaps
      by displacing elements along the minimum penetration axis (AABB SAT).
      Filters child objects to avoid redundant spatial conflicts.
          │
          ▼
  [5] SceneBuilder + Renderer (Blender / bpy)
      Configuration of lights, camera, and environment (HDRI).
      Automatic generation of floor and walls (Room Mode).
      Asset import with surface alignment via raycasting.
      Application of PBR materials and direct hierarchy management.
      Export in 2D (PNG) and 3D (GLB, USDZ) formats.
```

---

The intermediate JSON format produced by the model and consumed by Blender follows this schema:

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

All coordinates are expressed in Blender units (1 unit = 1 metre). Rotations are in radians using the Euler XYZ convention. RGB colors are normalized to the `[0.0, 1.0]` range.

---

## Repository Structure

```
Computer_Graphics_Project/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                 # Lint, test, security on push/PR
│   │   └── docker.yml             # Docker image build and push to GHCR
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   └── PULL_REQUEST_TEMPLATE.md
├── assets/
│   ├── models/                    # 3D assets (.obj, .fbx, .glb) — not versioned
│   └── renders/                   # PNG outputs generated by Blender
├── config/
│   ├── settings.yaml              # Main project configuration
│   └── prompts/
│       ├── system_prompt.txt      # System prompt for the LLM
│       └── multi_room_prompt.txt  # Advanced prompt for multi-room scenes
├── docs/
│   ├── architecture.md
│   ├── installation.md
│   ├── usage.md
│   └── contributing.md
├── src/
│   └── computer_graphics/
│       ├── __init__.py
│       ├── cli.py                 # CLI entry point (computer-graphics)
│       ├── config_loader.py       # YAML + .env config loading
│       ├── input_handler.py       # Stage 1: user input handling
│       ├── prompt_builder.py      # Stage 2: Ollama payload construction
│       ├── ollama_client.py       # Stage 3: HTTP client for Ollama
│       ├── json_parser.py         # Stage 4: robust JSON parsing
│       ├── validator.py           # Stage 4: Pydantic validation
│       │                          #          Supports SceneObject, LightObject,
│       │                          #          parent-child hierarchy, materials
│       ├── scene_graph.py         # Stage 4.5: spatial layout and collision
│       ├── orchestrator.py        # Pipeline coordination with agentic retry
│       └── blender/
│           ├── __init__.py
│           ├── scene_builder.py   # Scene construction, asset import,
│           │                      # surface snap, PBR materials
│           └── renderer.py        # PNG rendering and GLB/USDZ export
├── scripts/
│   ├── run_pipeline.py            # Main CLI entry point
│   ├── blender_runner.py          # Script executed inside Blender
│   ├── generate_primitives.py     # Automatic primitive 3D asset generator
│   └── setup_assets.py            # Asset library utilities
├── tests/
│   ├── conftest.py                # Shared fixtures
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

## System Requirements

| Component | Minimum Version | Notes |
|---|---|---|
| **Python** | 3.10+ | Required for `match`/`case` and modern type hints |
| **Git** | 2.40+ | Version control |
| **Blender** | 4.0+ | 3D scene construction and rendering |
| **Ollama** | Latest stable | Local AI server (separate installation) |
| **Disk space** | ~12 GB | Includes the AI model and 3D assets |

All paths in the commands below must be adapted to match the local environment.

---

## Quick Start Guide

This section covers the complete workflow from a text description to a 3D render in Blender.

### Section 1 — Starting Ollama

Ollama is the local AI server that processes text descriptions and generates 3D object coordinates. It must be running before the pipeline is executed.

**Option A (recommended):** Launch the Ollama application from the Start menu. It runs in the background and appears as an icon in the system tray.

**Option B:** Open a PowerShell terminal and run:

```powershell
ollama serve
```

> If Ollama is already running, the command will report an error on port 11434. This is expected and indicates the server is already active.

### Section 2 — Python Pipeline

Open a **new PowerShell terminal** and follow the steps below in order.

#### Step 1 — Navigate to the project directory

```powershell
cd C:\path\to\Computer_Graphics_Project
```

#### Step 2 — Activate the virtual environment

```powershell
.venv\Scripts\activate
```

A successful activation will display `(.venv)` at the start of the prompt.

#### Step 3 — Verify the Ollama connection

```powershell
python -c "from computer_graphics.ollama_client import OllamaClient; print(OllamaClient().health_check())"
```

The command should return `True`. If it returns `False`, verify that the Ollama server is running (Step 0 above).

#### Step 4 — Run the pipeline

```powershell
python scripts/run_pipeline.py "a room with a table and two chairs"
```

> If no model is specified, the system will prompt you to choose from those available on your Ollama server.

On completion, the following file is created in the project root:

```
scene_objects.json
```

### Section 3 — Blender Scene Construction and Rendering

#### Step 5 — Install Blender

Download Blender 4.0 or later from [https://www.blender.org/download/](https://www.blender.org/download/) and add its installation directory to the system `PATH`. Verify the installation:

```powershell
blender --version
```

#### Step 6 — Generate primitive 3D assets (one-time setup)

This step generates 12 base 3D models (table, chair, lamp, etc.) in `assets/models/`. It only needs to be run once.

```powershell
blender --background --python scripts/generate_primitives.py
```

The following assets are created: `table`, `chair`, `lamp`, `desk`, `sofa`, `bookshelf`, `monitor`, `plant`, `bed`, `cabinet`, `rug`, `fridge`.

#### Step 7 — Render the final scene

```powershell
blender --background --python scripts/blender_runner.py -- scene_objects.json --render assets/renders/output.png
```

The output PNG is saved to `assets/renders/output.png`. Rendering time depends on the system's hardware specifications.

### Complete Session Workflow

```powershell
# 1. Navigate to the project directory
cd C:\path\to\Computer_Graphics_Project

# 2. Activate the virtual environment
.venv\Scripts\activate

# 3. Verify the Ollama server connection
python -c "from computer_graphics.ollama_client import OllamaClient; print(OllamaClient().health_check())"

# 4. Generate the scene JSON file
python scripts/run_pipeline.py "scene description"

# 5. Build and render the scene in Blender
blender --background --python scripts/blender_runner.py -- scene_objects.json --render assets/renders/output.png
```

---

## Dependencies

### System Dependencies

| Component | Minimum Version | Notes |
|---|---|---|
| Python | 3.10 | Required for `match`/`case` and modern type hints |
| Blender | 4.0 | Required for Stage 5 (scene construction and rendering) |
| Ollama | Latest stable | Must be installed separately |
| Docker | 24.0 | Optional, required only for containerized mode |
| Git | 2.40 | Version control and pre-commit hooks |

### Python Dependencies (production)

| Package | Version | Purpose |
|---|---|---|
| `requests` | >=2.31.0 | HTTP communication with the Ollama server |
| `pyyaml` | >=6.0.1 | Reading `settings.yaml` configuration |
| `click` | >=8.1.7 | CLI interface |
| `rich` | >=13.7.0 | Formatted terminal output, tables, spinners |
| `pydantic` | >=2.5.0 | Scene object validation and serialization |

### Python Dependencies (development)

| Package | Version | Purpose |
|---|---|---|
| `pytest` | >=7.4.0 | Test framework |
| `pytest-cov` | >=4.1.0 | Test coverage |
| `pytest-mock` | >=3.12.0 | Mocking for unit tests |
| `ruff` | >=0.1.9 | Fast linter |
| `black` | >=23.12.0 | Code formatter |
| `mypy` | >=1.8.0 | Static type checking |
| `pre-commit` | >=3.6.0 | Git pre-commit hooks |
| `responses` | >=0.25.0 | HTTP call mocking in tests |
| `bandit` | >=1.7.0 | Static security analysis |
| `pip-audit` | >=2.6.0 | Dependency vulnerability scanning |

---

## Installation

### Prerequisites

Before proceeding, ensure the following are installed:

1. **Python 3.10+** — [Download](https://www.python.org/downloads/)
2. **Git** — [Download](https://git-scm.com/)
3. **Blender 4.0+** — [Download](https://www.blender.org/download/)
4. **LLM Provider** (choose one):
   - **Google Gemini** (Recommended): Create a free API key at [Google AI Studio](https://aistudio.google.com/).
   - **Ollama** (Offline): [Download](https://ollama.com) for local inference.

### Installing the Project

```powershell
# Clone the repository
git clone https://github.com/Anass-Chebbaki/Computer_Graphics_Project.git
cd Computer_Graphics_Project

# Create the Python virtual environment
python -m venv .venv

# Activate the virtual environment (Windows)
.venv\Scripts\activate

# Upgrade pip and install the project with development dependencies
python -m pip install --upgrade pip
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Copy the environment configuration file and add your API key
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=your_key
```

Verify the installation:

```powershell
# Verify LLM connectivity (defaults to Gemini if configured)
computer-graphics check
```

# Run the test suite
make test
```

### Generating Primitive Assets

If no 3D models are available, primitive assets can be generated automatically with Blender. The `scripts/generate_primitives.py` script constructs basic geometry and exports each object as an `.obj` file to `assets/models/`.

```powershell
blender --background --python scripts/generate_primitives.py
```

This enables a full demonstration of the pipeline — from text input to final render — without any external asset dependencies.

---

## Configuration

### `.env` File

Copy `.env.example` to `.env` and adjust the values to match the local environment:

```dotenv
# Ollama server URL
OLLAMA_URL=http://localhost:11434

# LLM model to use (optional, will prompt if empty)
# OLLAMA_MODEL=llama3

# HTTP request timeout in seconds
# Increase this value on slow hardware or when using large models
OLLAMA_TIMEOUT=180

# Path to the 3D asset directory
ASSETS_DIR=./assets/models

# Output directory for PNG renders
RENDER_OUTPUT_DIR=./assets/renders

# Maximum number of retries on invalid JSON
MAX_RETRIES=3

# Log level: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=INFO
```

Environment variables always take precedence over settings defined in `config/settings.yaml`. The loading order is: **environment variables → `.env` file → `settings.yaml` → default values**.

### `config/settings.yaml`

The YAML file centralizes all configuration parameters:

```yaml
ollama:
  url: "http://localhost:11434"
  model: null            # Set a model name here or leave null for interactive selection
  timeout: 180
  max_connection_retries: 3
  retry_delay: 2.0
  options:
    temperature: 0.2      # Low temperature for deterministic output
    top_p: 0.9
    num_predict: 1024     # Maximum token limit in the response

pipeline:
  max_retries: 3
  verbose: true

paths:
  assets_dir: "assets/models"
  render_output_dir: "assets/renders"
  prompt_file: "config/prompts/system_prompt.txt"

blender:
  render_engine: "CYCLES"   # Alternative: BLENDER_EEVEE
  resolution_x: 1920
  resolution_y: 1080
  samples: 64
  camera_location: [7.0, -7.0, 5.0]

validation:
  min_description_length: 10
  max_description_length: 2000
  max_coordinate_value: 50.0

room_mode:
  enabled: true
  margin: 2.0
  wall_height: 3.0
  ceiling: false
```

### System Prompt

The system prompt at `config/prompts/system_prompt.txt` is the most critical component for output quality. It instructs the model to respond exclusively with a valid JSON array conforming to the expected schema. The file can be modified to adjust the model's behaviour without touching the source code.

For complex scenes with many objects or multi-room layouts, the alternative prompt at `config/prompts/multi_room_prompt.txt` is available. It includes more detailed spatial guidelines and inter-zone distance constraints.

`PromptBuilder` loads the prompt using the following priority:

1. Text passed explicitly as a constructor argument
2. File specified via the `system_prompt_file` parameter
3. File at the conventional path `config/prompts/system_prompt.txt`
4. Default prompt hardcoded in `prompt_builder.py`

---

## Usage

### Activating the Environment

Always activate the virtual environment before running any commands:

```powershell
cd C:\path\to\Computer_Graphics_Project
.venv\Scripts\activate
```

### Generating the Scene JSON

```powershell
# Pass the description as a command-line argument
python scripts/run_pipeline.py "a kitchen with a table, two chairs, and a fridge"

# Interactive mode (description prompted at the terminal)
python scripts/run_pipeline.py --interactive
```

### Generating the 3D Render

```powershell
blender --background --python scripts/blender_runner.py -- scene_objects.json --render assets/renders/output.png
```

### Available Make Commands

```powershell
make demo                # Full demo with a predefined description
make pipeline            # Run the pipeline in interactive mode
make blender-run         # Build the Blender scene without rendering
make blender-render      # Build the Blender scene and generate a PNG render
make generate-primitives # Generate primitive 3D assets (.obj)
make check-assets        # Verify the asset library
make test                # Run the test suite
make test-cov            # Run tests with a coverage report
make lint                # Lint the codebase
make format              # Apply automatic code formatting
```

### Installed CLI (`computer-graphics`)

After `pip install -e .`, the `computer-graphics` command is available globally:

```bash
# Pass the description as an argument
computer-graphics generate "a kitchen with a table, two chairs, and a fridge"

# Interactive mode
computer-graphics generate --interactive

# Read the description from a text file
computer-graphics generate --file scene_description.txt

# Specify model, output file, and retry count
computer-graphics generate "desk with monitor" \
  --model mistral \
  --output desk.json \
  --retries 5

# Run the pipeline and launch Blender automatically
computer-graphics generate "scene description" --blender

# Run the pipeline, launch Blender, and generate a render
computer-graphics generate "scene description" --blender --render

# Check system prerequisites
computer-graphics check

# Display the current configuration
computer-graphics info

# Validate an existing scene JSON file
computer-graphics validate scene_objects.json
```

### `run_pipeline.py` Reference

Manages Stages 1–4.5 (input → collision-free JSON layout) and saves the result to a JSON file:

```bash
# Pass description as argument
python scripts/run_pipeline.py "a meeting room with a desk, four chairs, and a lamp"

# Interactive mode
python scripts/run_pipeline.py --interactive

# Read from file
python scripts/run_pipeline.py --file scene_description.txt

# All parameters
python scripts/run_pipeline.py \
  "a meeting room with a desk, four chairs, and a lamp" \
  --model mistral \
  --output meeting_room.json \
  --retries 5 \
  --ollama-url http://localhost:11434 \
  --verbose
```

### `blender_runner.py` Reference

Manages Stage 5 (JSON → 3D scene) and is designed to be executed inside Blender:

```bash
# Build scene from generated JSON
blender --background --python scripts/blender_runner.py -- scene_objects.json

# Build scene and render to PNG
blender --background --python scripts/blender_runner.py \
  -- scene_objects.json \
  --render assets/renders/output.png

# Build scene without rendering
blender --background --python scripts/blender_runner.py \
  -- scene_objects.json \
  --no-render
```

### Using as a Python Library

```python
from computer_graphics.orchestrator import generate_scene_objects
from computer_graphics.ollama_client import OllamaClient

# Verify Ollama is reachable
client = OllamaClient()
if not client.health_check():
    raise RuntimeError("Ollama is not reachable. Run: ollama serve")

# Run the pipeline (includes collision-free layout)
objects = generate_scene_objects(
    scene_description="a room with a table, a chair, and a floor lamp",
    model="llama3",
    max_retries=3,
    ollama_url="http://localhost:11434",
    timeout=180,
    verbose=True,
)

# Each object is a Pydantic instance with direct attribute access
for obj in objects:
    print(f"{obj.name}: x={obj.x:.2f}, y={obj.y:.2f}, z={obj.z:.2f}, scale={obj.scale:.2f}")

# Serialize to dict or JSON
import json
data = [obj.model_dump() for obj in objects]
print(json.dumps(data, indent=2))
```

### Running from the Blender Text Editor

To run the script directly from Blender's internal editor without using a terminal:

1. Open Blender and navigate to the **Text Editor** workspace.
2. Open `scripts/blender_runner.py`.
3. Edit the `CONFIG` section at the top of the file:
   ```python
   OBJECTS_JSON_PATH: str = "/absolute/path/to/scene_objects.json"
   ASSETS_DIR: str = "/absolute/path/to/assets/models"
   RENDER_OUTPUT: str = "/absolute/path/to/assets/renders/output.png"
   RENDER_ENABLED: bool = True
   ```
4. Click **Run Script**.

---

## CLI Reference

### `computer-graphics generate`

```
Usage: computer-graphics generate [OPTIONS] [DESCRIPTION]

Arguments:
  DESCRIPTION           Scene description text

Options:
  -i, --interactive     Prompt for the description interactively
  -f, --file PATH       Read the description from a .txt file
  -m, --model TEXT      Ollama model name [default: dynamic selection]
  -o, --output PATH     JSON output file  [default: scene_objects.json]
  -r, --retries INT     Maximum number of retries  [default: 3]
  --ollama-url TEXT     Ollama server URL  [default: http://localhost:11434]
  -v, --verbose         Detailed debug output
  -b, --blender         Automatically launch Blender on completion
  --render              Generate a PNG render (requires --blender)
  --render-output PATH  PNG output path  [default: assets/renders/output.png]
  --export-glb          Export the scene in .glb format
  --export-usdz         Export the scene in .usdz format
  --export-output PATH  Base path for 3D export files
  --help                Show this message and exit
```

### `python scripts/run_pipeline.py`

```
Usage: python scripts/run_pipeline.py [OPTIONS] [DESCRIPTION]

Options:
  -i, --interactive     Prompt for the description interactively
  -f, --file PATH       Read the description from a .txt file
  -m, --model TEXT      Ollama model name [default: dynamic selection]
  -o, --output PATH     JSON output file  [default: scene_objects.json]
  -r, --retries INT     Maximum number of retries  [default: 3]
  --ollama-url TEXT     Ollama server URL  [default: http://localhost:11434]
  -v, --verbose         Detailed debug output
  --help                Show this message and exit
```

### `blender --background --python scripts/blender_runner.py`

```
Usage: blender --background --python scripts/blender_runner.py -- [OPTIONS] JSON_PATH

Positional Arguments:
  JSON_PATH             Path to the JSON file generated by the pipeline

Options:
  --render PATH         Enable rendering and save the PNG to the specified path
  --no-render           Disable rendering (build the scene only)
```

### Makefile Commands

```
install              Install production dependencies
install-dev          Install all dependencies including development packages
lint                 Run ruff linter on src/, tests/, scripts/
format               Format the code with black and ruff --fix
type-check           Static type checking with mypy
test                 Run the test suite with pytest
test-cov             Run tests with an HTML coverage report in htmlcov/
coverage-open        Open the coverage report in the browser
ollama-start         Start the Ollama server in the background
ollama-pull          Download the specified model (e.g. make ollama-pull MODEL=llama3)
ollama-status        Show available models in the local server
pipeline             Run the pipeline in interactive mode
demo                 Quick run with a hardcoded example description
blender-run          Launch Blender with the scene-building script
blender-render       Launch Blender with scene construction and PNG rendering
generate-primitives  Generate primitive 3D assets with Blender
check-assets         Check the status of the asset library
asset-report         Generate a JSON asset report
cli-check            Verify system prerequisites via the CLI
cli-info             Display configuration via the CLI
cli-demo             Full demo via the computer-graphics command
cli-validate         Validate the current JSON output
docker-build         Build the Docker image
docker-up            Start all services with Docker Compose
docker-down          Stop Docker services
docker-logs          Stream live container logs
clean                Remove temporary files, caches, and build artefacts
```

---

## Advanced Features

### 2D Spatial Preview

To validate the spatial layout before proceeding to Blender, a top-down 2D preview can be generated:

```bash
python -m computer_graphics.cli "a room with a table and four chairs" --preview
```

This produces a `preview.png` file showing the bounding boxes of all scene objects.

### Multi-LLM Support

The system supports swappable LLM providers. To use OpenAI instead of Ollama, configure the `llm` section in `settings.yaml`:

```yaml
llm:
  provider: "openai"   # or "ollama"
  api_key: "your-key"
  base_url: "https://api.openai.com/v1"
```

### Color Override

Objects can receive an RGB color override directly from the language model. This value is blended with the chosen procedural material:

```json
{
  "name": "chair",
  "material_semantics": "fabric",
  "color_override": [0.2, 0.4, 0.8]
}
```

### Parent-Child Hierarchy

Scene objects support a parent-child relationship via the `parent` field. Child object coordinates are relative to the parent:

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

`SceneBuilder` automatically creates parent-child constraints (`parent_set()`) in Blender and applies relative transformations.

### Light Sources

The model can generate light sources alongside regular objects. Each source is represented by a `LightObject` with the following properties:

- **Type**: `POINT` (omni-directional), `SUN` (infinite directional), `SPOT` (focused cone), `AREA` (surface emission)
- **Color**: Normalized RGB triple `[0.0, 1.0]` per channel (e.g. white: `[1.0, 1.0, 1.0]`, warm: `[1.0, 1.0, 0.8]`)
- **Intensity**: `energy` in Watts (Cycles) or arbitrary units (EEVEE)
- **Spot angle** (SPOT only): `spot_size` in radians (~0.785 rad ≈ 45°)

Example:

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

### Procedural Materials

The `material_semantics` field allows the model to specify the material type declaratively. `SceneBuilder` applies the corresponding procedural shader:

| Semantic | Description | Properties | Shader |
|---|---|---|---|
| `wood` | Wood | Brown diffuse, bump, grain | Procedural wood |
| `glass` | Transparent glass | IOR 1.45, translucency | Glass BSDF |
| `fabric` | Soft fabric | Satin diffuse, micro-roughness | Diffuse + Coat |
| `metal` | Shiny metal | High specular, metallic IOR | Metal BSDF |
| `plastic` | Plastic | Light diffuse, medium specular | Diffuse + Glossy |
| `concrete` | Concrete | Grey diffuse, high roughness, pores | Procedural |
| `ceramic` | Ceramic | Subtle gloss, thin specular | Glossy + Diffuse |
| `leather` | Leather | Dark brown, anisotropic | Anisotropic |
| `marble` | Marble | White, fine veining, specular | Procedural |
| `rubber` | Rubber | Matt black, high roughness | Matte |

### PBR Texture Support

Shader parameters (metallic, roughness, IOR, etc.) are defined in `config/materials.yaml`. The system supports automatic PBR texture application if textures are present in the following structure:

```
assets/textures/<material_semantics>/[albedo|roughness|normal|displacement].[png|jpg]
```

### Surface Snap

The system uses raycasting to detect surfaces beneath objects (floors, shelves, etc.) and automatically corrects the Z coordinate to ensure physical contact. Self-collision of the source object is excluded to prevent positioning errors.

### Automatic Collision Resolution

The **SceneGraph** stage automatically detects AABB bounding box overlaps and applies iterative coordinate adjustments to resolve them. If collisions cannot be resolved spatially (too many objects in a constrained area), an **agentic retry loop** is triggered:

1. **Detection**: SceneGraph computes scene density (objects per square metre).
2. **Analysis**: If density exceeds the threshold and collisions remain, identifies the most problematic pair.
3. **Feedback**: Generates an explicit instruction for the model: *"Increase the distance between `object_a` and `object_b` by at least 1.5 metres."*
4. **Regeneration**: Sends the feedback to the model via the conversation loop, requesting new coordinates.
5. **Iteration**: Repeats for up to 3 attempts (configurable via `--retries`).

This ensures that even complex scenes converge to a physically valid layout without manual post-processing.

---

## 3D Assets

The `assets/models/` directory must contain the 3D model files. The system indexes files recursively and uses a TF-IDF search with IDF weights to find the asset most similar to a given text query.

**Supported formats:**

- `.obj` (Wavefront OBJ)
- `.fbx` (Autodesk FBX)
- `.glb` / `.gltf` (GL Transmission Format)

The system supports parsing dimensional metadata from GLB files to compute accurate object bounding boxes.

### Default Asset Library

| Asset file | Object | Approximate dimensions |
|---|---|---|
| `table.obj` | Table | 1.5 × 0.9 × 0.75 m |
| `chair.obj` | Chair | 0.6 × 0.6 × 1.0 m |
| `lamp.obj` | Floor lamp | 0.4 × 0.4 × 1.8 m |
| `desk.obj` | Desk | 1.6 × 0.8 × 0.75 m |
| `sofa.obj` | Sofa | 2.2 × 0.9 × 0.9 m |
| `bookshelf.obj` | Bookshelf | 0.9 × 0.3 × 1.8 m |
| `monitor.obj` | Monitor | 0.6 × 0.2 × 0.4 m |
| `bed.obj` | Bed | 1.6 × 2.0 × 0.6 m |
| `plant.obj` | Potted plant | 0.5 × 0.5 × 1.0 m |
| `cabinet.obj` | Cabinet | 0.8 × 0.4 × 1.4 m |
| `fridge.obj` | Fridge | 0.7 × 0.7 × 1.8 m |
| `rug.obj` | Rug | 2.0 × 1.5 × 0.02 m |

If an asset is not found, the system automatically creates a semi-transparent red proxy cube at the expected coordinates. This allows the spatial layout to be verified before all final assets are available.

Object dimensions are used by `scene_graph.py` for bounding box calculation and collision resolution.

### Free Asset Sources

- [Poly Haven](https://polyhaven.com) — `.glb` models, CC0 license
- [Sketchfab](https://sketchfab.com/features/free-3d-models) — various formats, mixed licenses
- [BlendSwap](https://www.blendswap.com) — native Blender models
- [OpenGameArt](https://opengameart.org) — open formats, free licenses

Binary asset files are not included in the repository. For repositories with large model files, [Git LFS](https://git-lfs.com) is recommended.

### Asset Library Verification

```bash
# Check which assets are present and which are missing
python scripts/setup_assets.py check

# Generate a full JSON report with dimensions and suggested sources
python scripts/setup_assets.py report --output asset_report.json
```

---

## Development

### Recommended Workflow

```bash
# Activate the virtual environment
source .venv/bin/activate

# Install development dependencies (if not already done)
make install-dev

# Install pre-commit hooks
pre-commit install

# Standard development cycle
make lint          # Check code style
make format        # Apply automatic formatting
make type-check    # Verify type correctness
make test          # Run the test suite
make test-cov      # Run tests with coverage report
```

### Code Conventions

- **Formatter**: `black` with a maximum line length of 88 characters
- **Linter**: `ruff` with rulesets `E`, `F`, `W`, `I`, `N`, `UP`, `ANN`, `B`, `C4`, `SIM`
- **Type checking**: `mypy` in strict mode for all internal modules
- **Docstrings**: Google style for all public methods
- **Type annotations**: mandatory for all public functions
- **Imports**: ordered with `isort` (integrated in ruff via ruleset `I`)
- **Commits**: [Conventional Commits](https://www.conventionalcommits.org/) format (`feat:`, `fix:`, `docs:`, `test:`, etc.)

Pre-commit hooks enforce these conventions automatically before each commit. To run all checks manually:

```bash
pre-commit run --all-files
```

### Module Overview

Each module corresponds to a specific pipeline stage.

Modules under `src/computer_graphics/blender/` depend on `bpy` and can only be imported inside a Blender process. Do not import them in a standard Python context — they will raise an `ImportError`.

`orchestrator.py` is the main coordination point. It instantiates the Stage 1–4.5 components, manages the retry logic, and produces the final list of validated, collision-free `SceneObject` instances. It is the recommended entry point for programmatic use of the pipeline.

`scene_graph.py` implements a spatial layout system using Axis-Aligned Bounding Boxes (AABB). Larger objects retain the position generated by the model; smaller objects are displaced along the minimum penetration direction when an overlap is detected. The system iterates until convergence or until the configured maximum number of iterations is reached.

`config_loader.py` handles priority-merged configuration loading from `.env`, `settings.yaml`, and default values. It exposes a simple interface via `ConfigLoader.load()` and `ConfigLoader.get("section", "key")`.

### Adding a New Object Type

To add support for a new asset (e.g. `"wardrobe"`):

1. Add the name to `KNOWN_ASSET_NAMES` in `src/computer_graphics/validator.py`.
2. Add the real-world dimensions to `OBJECT_DIMENSIONS` in `src/computer_graphics/scene_graph.py`.
3. Add the geometric definition to `ASSET_DEFINITIONS` in `scripts/generate_primitives.py`.
4. Add `wardrobe.obj` (or generate it with `make generate-primitives`) to `assets/models/`.

---

## Testing

### Running Tests

```bash
# Full test suite
make test

# With terminal and HTML coverage report
make test-cov

# Open the HTML report in the browser
make coverage-open

# A specific module
pytest tests/test_json_parser.py -v

# A specific class or method
pytest tests/test_validator.py::TestValidateObjects::test_raises_on_empty_list -v

# With detailed log output
pytest tests/ -v --log-cli-level=DEBUG
```

### Test Organisation

| Test file | Module under test | Main technique |
|---|---|---|
| `test_input_handler.py` | `input_handler.py` | Validation, factory methods, interactive mock |
| `test_prompt_builder.py` | `prompt_builder.py` | Payload structure, prompt loading from file |
| `test_ollama_client.py` | `ollama_client.py` | HTTP mock with `responses`, health check |
| `test_json_parser.py` | `json_parser.py` | Clean and dirty inputs, edge cases |
| `test_validator.py` | `validator.py` | Pydantic validation, type coercion |
| `test_scene_graph.py` | `scene_graph.py` | AABB, collision detection and resolution |
| `test_orchestrator.py` | `orchestrator.py` | Integration tests with mocks, retry logic |

Modules that depend on `bpy` (Stage 5) are not included in the standard test suite, as they require an active Blender process. They must be tested manually or via a smoke test script executed inside Blender.

### Fixtures

Shared fixtures are defined in `tests/conftest.py`:

- `sample_clean_json`: ideal model JSON output, ready for parsing
- `sample_dirty_text`: text with markdown backticks, JavaScript comments, and trailing commas (a common real-world case)
- `valid_objects_list`: list of normalised dictionaries for validator tests
- `mock_ollama_response`: simulated JSON structure of an Ollama HTTP response

Files in `tests/fixtures/` contain real model output examples used in parametrized tests.

---

## Docker

### Without Blender (LLM Pipeline Only)

The `docker/Dockerfile` runs only Stages 1–4.5 of the pipeline. Blender is not included in the image due to its size; the produced JSON file must then be used with a local Blender installation.

```bash
# Build the image
make docker-build

# Run with a description as argument
docker run --rm \
  -v $(pwd)/assets:/app/assets \
  -v $(pwd)/output:/app/output \
  --add-host=host.docker.internal:host-gateway \
  computer-graphics:latest \
  "a room with a table and a chair" \
  --output /app/output/scene_objects.json
```

### Docker Compose (Full Pipeline + Containerised Ollama)

`docker-compose.yml` defines two services:

- `ollama`: Ollama server in a container with optional GPU support (NVIDIA)
- `computer-graphics`: Python pipeline depending on the `ollama` service

```bash
# Start all services
make docker-up

# Stream live logs for both services
make docker-logs

# Stop and remove the containers
make docker-down
```

The `ollama_data` volume is persistent: downloaded models survive container restarts and do not need to be re-downloaded.

`entrypoint.sh` automatically waits for Ollama to be ready before starting the pipeline, downloads the model if it is not already present in the volume, and handles errors cleanly.

To enable NVIDIA GPU support, ensure `nvidia-container-toolkit` is installed on the host. The `deploy.resources.reservations.devices` section in `docker-compose.yml` is already configured for this.

---

## CI/CD

### `ci.yml` — Continuous Integration

Runs on every push and pull request to `main` and `develop`. Consists of four parallel jobs:

- **lint**: runs `ruff`, `black --check`, and `mypy` on Python 3.11 (Ubuntu)
- **test**: runs pytest with coverage on a matrix of 9 combinations (3 OS × 3 Python versions: 3.10, 3.11, 3.12); the coverage report is uploaded to Codecov
- **security**: runs `bandit` for static security analysis and `pip-audit` to check for known vulnerabilities in dependencies
- **coverage-report**: coverage gate with a configurable minimum threshold; blocks merge if coverage falls below it

The workflow uses `concurrency` with `cancel-in-progress: true` to avoid redundant runs on the same branch.

### `docker.yml` — Docker Image Build

Runs on pushes to `main` and on creation of semantic version tags (`v*`). Builds the Docker image and publishes it to the GitHub Container Registry (GHCR) with tags corresponding to the branch or version.

### Local Pre-commit Hooks

The following checks run locally before each commit:

- `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-json`, `check-toml`
- `check-merge-conflict`, `check-added-large-files` (10 MB limit)
- `debug-statements`, `detect-private-key`
- `black` — code formatting
- `ruff` — linting with automatic fixes
- `mypy` — type checking with additional type stubs

---

## Troubleshooting

### Ollama Server Not Responding

```
OllamaConnectionError: Unable to connect to Ollama at http://localhost:11434
```

Verify the server is running:

```bash
# Check whether the process is active
ps aux | grep "ollama serve"

# If not active, start it
ollama serve

# Verify the response
curl http://localhost:11434/api/tags
```

The built-in diagnostic command can also be used:

```bash
computer-graphics check
```

If running in Docker and the container cannot reach Ollama on the host, verify that `--add-host=host.docker.internal:host-gateway` is present in the `docker run` command, or that the `ollama` service is defined in `docker-compose.yml`.

### Model Returns Invalid JSON

The parser implements three extraction strategies in cascade (direct parsing, regex, aggressive cleaning). If all strategies fail after `max_retries` attempts, a `RuntimeError` is raised.

Possible causes and solutions:

- **Temperature too high**: lower `temperature` in `config/settings.yaml` (recommended: 0.1–0.2)
- **Model too small**: use `llama3` or `mistral` instead of 1–3B parameter models
- **Ambiguous description**: rephrase the description more explicitly, listing objects one by one
- **Timeout**: increase `OLLAMA_TIMEOUT` in `.env` if the model takes longer than 180 seconds

To diagnose the issue, enable debug logging:

```bash
python scripts/run_pipeline.py "description" --verbose
# or
computer-graphics generate "description" --verbose
```

### Asset Not Found

```
WARNING: Asset 'sofa' not found in assets/models. Creating proxy cube.
```

The system continues execution by creating a semi-transparent red proxy cube. To resolve:

1. Add `assets/models/sofa.obj` (or `.fbx`, `.glb`).
2. Alternatively, run `make generate-primitives` to generate a primitive asset.
3. Verify that the filename exactly matches the value of the `"name"` field in the JSON.

```bash
# Display a full report of present and missing assets
make check-assets
```

### Pydantic Import Error

```
ImportError: cannot import name 'field_validator' from 'pydantic'
```

The project requires Pydantic v2. Verify the installed version:

```bash
python -c "import pydantic; print(pydantic.VERSION)"
pip install "pydantic>=2.5.0"
```

### Blender Cannot Find Project Modules

```
ModuleNotFoundError: No module named 'computer_graphics'
```

`blender_runner.py` automatically adds `src/` to `sys.path`. If the error persists, verify that the script is run from the repository root:

```bash
# Correct: relative path from the root
blender --background --python scripts/blender_runner.py -- scene_objects.json

# Incorrect: running from a subdirectory
cd scripts && blender --background --python blender_runner.py -- ../scene_objects.json
```

---

## Output JSON Structure

The JSON file produced by the pipeline (default: `scene_objects.json`) contains an array of objects with the following structure:

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

| Field | Type | Description |
|---|---|---|
| `name` | string | Object name in lowercase English; must match the asset filename |
| `x` | float | Position on the X axis in Blender units (1 unit = 1 metre) |
| `y` | float | Position on the Y axis in Blender units |
| `z` | float | Position on the Z axis (0.0 = floor level) |
| `rot_x` | float | Rotation around the X axis in radians |
| `rot_y` | float | Rotation around the Y axis in radians |
| `rot_z` | float | Rotation around the Z axis in radians |
| `scale` | float | Uniform scale factor (1.0 = original asset dimensions) |

The JSON file can be edited manually before passing it to Blender for fine layout adjustments, and validated with:

```bash
computer-graphics validate scene_objects.json
```

---

## License

This project is distributed under the MIT License. See the [LICENSE](LICENSE) file for the full text.
