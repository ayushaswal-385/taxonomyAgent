#!/usr/bin/env python3
"""
MCAT Taxonomy Pipeline — Entry Point (v7.0)

Pipeline architecture:
  Per-MCAT loop:
    Wave 0  → Agent 1 (PDF), Agent 2 (Image Verifier)
    Wave 1  → Agent 3 (Context + Market Research) — receives taxonomy_context
    Wave 2  → Agents 4-11 (parallel) — Agent 4 reads in-zip agent4_input.json
    Wave 3a → Agent 12 (Name Generator)
    Wave 3b → Agent 14 (Structural Verdict)
    Wave 4  → Consolidator  →  {slug}_context.json + {slug}_related_mcat_context.json

Usage:
  1. Place input zip(s) in input/
  2. Ensure each zip contains agent4_input.json plus the usual MCAT input files
  3. python run_pipeline.py
"""
import os
import sys
import time
import shutil

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from pipeline.config import INPUT_DIR, OUTPUT_DIR
from pipeline.file_resolver import discover_input_zips, extract_zip, resolve_files
from pipeline.orchestrator import run_pipeline_for_zip


def main():
    print("=" * 70)
    print("  MCAT TAXONOMY PIPELINE v7.0")
    print("  Model: anthropic/claude-sonnet-4-6 via LiteLLM")
    print("=" * 70)

    # Discover input zips
    zips = discover_input_zips(INPUT_DIR)
    if not zips:
        print(f"\nNo zip files found in {INPUT_DIR}")
        sys.exit(1)

    print(f"\nFound {len(zips)} input zip(s):")
    for z in zips:
        print(f"  → {os.path.basename(z)}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    total_start = time.time()

    # ── PER-ZIP PIPELINE ───────────────────────────────────────────────────────
    for zip_idx, zip_path in enumerate(zips):
        zip_name = os.path.splitext(os.path.basename(zip_path))[0]
        print(f"\n{'*' * 70}")
        print(f"  ZIP {zip_idx + 1}/{len(zips)}: {zip_name}")
        print(f"{'*' * 70}")

        output_dir  = os.path.join(OUTPUT_DIR, zip_name)
        work_dir    = os.path.join(PROJECT_ROOT, "_work", zip_name)
        extract_dir = os.path.join(work_dir, "extracted")

        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(work_dir, exist_ok=True)

        # Extract zip
        if not os.path.isdir(extract_dir):
            print(f"\nExtracting {zip_name}.zip ...")
            extract_zip(zip_path, extract_dir)

        files = resolve_files(extract_dir)

        print(f"\nResolved files:")
        for key, path in sorted(files.items()):
            if isinstance(path, list):
                print(f"  {key}: {len(path)} files")
                for p in path:
                    print(f"    → {os.path.basename(p)}")
            elif path:
                print(f"  {key}: ✓ {os.path.basename(path)}")
            else:
                print(f"  {key}: ✗ not found")

        if not files.get("agent4_input"):
            print(f"\n  ⚠ agent4_input.json missing in {zip_name}.zip, skipping this MCAT.")
            continue

        zip_start = time.time()
        tracker = run_pipeline_for_zip(zip_name, files, output_dir, work_dir)
        zip_elapsed = time.time() - zip_start

        print(f"\n{'='*60}")
        print(f"  ZIP '{zip_name}' completed in {zip_elapsed/60:.1f} minutes")
        print(f"{'='*60}")

    total_elapsed = time.time() - total_start
    print(f"\n{'*' * 70}")
    print(f"  ALL DONE — Total time: {total_elapsed/60:.1f} minutes")
    print(f"  Output directory: {OUTPUT_DIR}")
    print(f"{'*' * 70}")


if __name__ == "__main__":
    main()
