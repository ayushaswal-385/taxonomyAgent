#!/usr/bin/env python3
"""
MCAT Taxonomy Pipeline — Entry Point (v7.0)

Pipeline architecture:
  Pre-Pipeline (once, across all MCATs):
    catalogue_preprocessor.py  →  agent4_input/{mcat_id}/agent4_input.json

  Per-MCAT loop:
    Wave 0  → Agent 1 (PDF), Agent 2 (Image Verifier)
    Wave 1  → Agent 3 (Context + Market Research) — receives taxonomy_context
    Wave 2  → Agents 4-11 (parallel) — Agent 4 reads agent4_input.json
    Wave 3a → Agent 12 (Name Generator)
    Wave 3b → Agent 14 (Structural Verdict)
    Wave 4  → Consolidator  →  {slug}_context.json + {slug}_related_mcat_context.json

Usage:
  1. Place input zip(s) in input/
  2. Ensure catalogue data files are present for the preprocessor (see README)
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
from pipeline.file_resolver import discover_input_zips, extract_zip, resolve_files, read_csv_safe
from pipeline.orchestrator import run_pipeline_for_zip

# Pre-pipeline uses the standalone catalogue_preprocessor
import catalogue_preprocessor as cp

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION — catalogue data files for the preprocessor
# These are shared across the full batch and do NOT change per-MCAT.
# ─────────────────────────────────────────────────────────────────────────────
PREPROCESSOR_CONFIG = {
    # Path to the full ~98K MCAT catalogue
    "all_mcats":  os.path.join(PROJECT_ROOT, "input", "all_mcats_indiamart.csv"),
    # Taxonomy tree (MCAT Level, PMCAT, listing_count, etc.)
    "tree":       os.path.join(PROJECT_ROOT, "input", "taxonomy_tree.csv"),
    # Overlap data (quantitative product/supplier overlap between MCAT pairs)
    "overlap":    os.path.join(PROJECT_ROOT, "input", "related_mcats_overlap.csv"),
    # Platform-level existing related-category links
    "platform":   os.path.join(PROJECT_ROOT, "input", "mcat_related_categories.csv"),
    # Output directory for agent4_input/{mcat_id}/agent4_input.json
    "output_dir": os.path.join(PROJECT_ROOT, "agent4_input"),
}


def run_pre_pipeline(mcat_list_path: str, target_mcat_names: list, zip_overlap_path: str = None, zip_platform_path: str = None) -> bool:
    """Run catalogue_preprocessor.py once across the full mcat_list batch.

    Reads PREPROCESSOR_CONFIG paths. Generates one agent4_input.json per MCAT.
    Returns True on success, False if required files are missing.
    """
    print("\n" + "=" * 70)
    print("  PRE-PIPELINE: catalogue_preprocessor.py")
    print("=" * 70)

    # Check required files
    missing = []
    for key in ("all_mcats", "tree"):
        if not os.path.isfile(PREPROCESSOR_CONFIG[key]):
            missing.append(f"  ✗ {key}: {PREPROCESSOR_CONFIG[key]}")

    if not os.path.isfile(mcat_list_path):
        missing.append(f"  ✗ mcat_list: {mcat_list_path}")

    if missing:
        print("\nERROR: Required preprocessor input files not found:")
        for m in missing:
            print(m)
        print("\nProvide these files and rerun. See README for column specifications.")
        return False

    # Use zip-provided files if available, otherwise fallback to global PREPROCESSOR_CONFIG
    overlap_path  = zip_overlap_path if zip_overlap_path and os.path.isfile(zip_overlap_path) else PREPROCESSOR_CONFIG["overlap"]
    overlap_path  = overlap_path if os.path.isfile(overlap_path) else None

    platform_path = zip_platform_path if zip_platform_path and os.path.isfile(zip_platform_path) else PREPROCESSOR_CONFIG["platform"]
    platform_path = platform_path if os.path.isfile(platform_path) else None

    if not overlap_path:
        print(f"  ⚠ Overlap CSV not found (checked zip and global) — Tier 2 skipped")
    if not platform_path:
        print(f"  ⚠ Platform CSV not found (checked zip and global) — Tier 3 skipped")

    # Startup: load all source files once
    cp.startup(
        PREPROCESSOR_CONFIG["all_mcats"],
        PREPROCESSOR_CONFIG["tree"],
        overlap_path,
        platform_path,
    )

    # Read mcat_list
    mcat_rows = read_csv_safe(mcat_list_path)
    if not mcat_rows:
        print(f"ERROR: mcat_list is empty or unreadable: {mcat_list_path}")
        return False

    target_mcat_names_lower = [name.lower() for name in target_mcat_names]
    target_rows = [
        row for row in mcat_rows
        if (row.get("mcat_name", row.get("glcat_mcat_name", ""))).strip().lower() in target_mcat_names_lower
    ]
    
    if not target_rows:
        print(f"  ⚠ No rows found matching the target zip names, running for all rows as fallback.")
        target_rows = mcat_rows

    output_dir = PREPROCESSOR_CONFIG["output_dir"]
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n  Processing {len(target_rows)} required MCATs → {output_dir}/")
    start = time.time()

    success = 0
    for row in target_rows:
        mcat_id   = str(row.get("mcat_id",   row.get("glcat_mcat_id",   ""))).strip()
        mcat_name =     row.get("mcat_name", row.get("glcat_mcat_name", "")).strip()
        if not mcat_id or not mcat_name:
            print(f"  ⚠ Skipping row with missing mcat_id or mcat_name: {row}")
            continue

        # Skip if already generated (re-run only when source data changes)
        out_file = os.path.join(output_dir, mcat_id, "agent4_input.json")
        if os.path.isfile(out_file):
            print(f"  ↩ [{mcat_id}] {mcat_name} — already exists, skipping")
            success += 1
            continue

        try:
            cp.preprocess(mcat_id, mcat_name, output_dir)
            success += 1
        except Exception as e:
            print(f"  ✗ [{mcat_id}] {mcat_name} — preprocessor error: {e}")

    elapsed = time.time() - start
    print(f"\n  Pre-pipeline complete: {success}/{len(target_rows)} MCATs in {elapsed:.1f}s")
    return True


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

    # (Pre-pipeline is now run per-zip inside the loop below)
    agent4_input_base_dir = PREPROCESSOR_CONFIG["output_dir"]

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

        # ── Run pre-pipeline for this specific zip ────────────────────────────
        mcat_list_path = files.get("mcat_list") or os.path.join(PROJECT_ROOT, "input", "mcat_list.csv")
        overlap_path = files.get("overlap")
        platform_path = files.get("mcat_related")

        pre_ok = run_pre_pipeline(
            mcat_list_path, 
            [zip_name], 
            zip_overlap_path=overlap_path, 
            zip_platform_path=platform_path
        )
        
        if not pre_ok:
            print(f"\n  ⚠ Pre-pipeline failed for {zip_name}, skipping this MCAT.")
            continue

        zip_start = time.time()
        tracker = run_pipeline_for_zip(
            zip_name, files, output_dir, work_dir,
            agent4_input_base_dir=agent4_input_base_dir,
        )
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
