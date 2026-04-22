#!/usr/bin/env python3
"""
Script per verificare che il coverage sia al di sopra dei threshold richiesti.

Verifica:
- Coverage globale >= 90%
- Coverage singoli file >= 85%

Uso:
    python scripts/check_coverage.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


# Setup path
PROJECT_ROOT = Path(__file__).parent.parent

# Thresholds
GLOBAL_THRESHOLD = 90
FILE_THRESHOLD = 85


def run_coverage_test() -> bool:
    """Esegue pytest con coverage e controlla i threshold."""
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "--cov=src/computer_graphics",
            "--cov-report=json",
            "--cov-report=term-missing",
            "-q",
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )

    # Leggi il report JSON di coverage
    if not (PROJECT_ROOT / "coverage.json").exists():
        print("❌ Errore: coverage.json non generato")
        return False

    try:
        with open(PROJECT_ROOT / "coverage.json") as f:
            coverage_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"❌ Errore lettura coverage.json: {exc}")
        return False

    # Estrai i dati per file
    summary = coverage_data.get("totals", {})
    global_percent = summary.get("percent_covered", 0)

    print("\n📊 Coverage Report")
    print("==================\n")
    print(f"Global Coverage: {global_percent:.2f}% (threshold: {GLOBAL_THRESHOLD}%)")

    if global_percent < GLOBAL_THRESHOLD:
        print("❌ Global coverage BELOW threshold!")
        return False

    print("✅ Global coverage OK\n")

    # Verifica coverage per file
    files = coverage_data.get("files", {})
    all_files_ok = True

    print("Per-file Coverage Check (threshold: 85%):")
    print("-" * 50)

    for filepath, data in sorted(files.items()):
        # Check both Unix and Windows paths
        if not ("computer_graphics" in filepath and "tests" not in filepath):
            continue

        file_percent = data.get("summary", {}).get("percent_covered", 0)
        status = "✅" if file_percent >= FILE_THRESHOLD else "❌"

        # Estrai solo il nome del file
        filename = Path(filepath).name
        print(f"{status} {filename:30s} {file_percent:6.2f}%")

        if file_percent < FILE_THRESHOLD:
            all_files_ok = False

    print("-" * 50)

    if not all_files_ok:
        print(f"\n❌ Some files are BELOW {FILE_THRESHOLD}% threshold!")
        return False

    print(f"\n✅ All files are above {FILE_THRESHOLD}% threshold!")
    return True


if __name__ == "__main__":
    success = run_coverage_test()
    sys.exit(0 if success else 1)
