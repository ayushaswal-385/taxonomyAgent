"""Orchestrator — Wave execution controller for the MCAT taxonomy pipeline (v7.0)."""
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pipeline.config import MAX_PARALLEL_AGENTS
from pipeline.file_resolver import read_csv_safe, get_mcat_slug
from pipeline.image_preloader import preload_images, load_image_for_vision
from pipeline.llm_client import LLMClient
from pipeline.token_tracker import TokenTracker
from pipeline.agents.wave0 import run_agent_01, run_agent_02
from pipeline.agents.wave1 import run_agent_03
from pipeline.agents.wave2 import (run_agent_04, run_agent_05, run_agent_06,
                                    run_agent_07, run_agent_08, run_agent_09,
                                    run_agent_10, run_agent_11)
from pipeline.agents.wave3 import run_agent_12, run_agent_14
from pipeline.agents.consolidator import run_consolidator


# ─────────────────────────────────────────────────────────────────────────────
# HELPER — load agent4_input.json from the extracted zip
# ─────────────────────────────────────────────────────────────────────────────

def load_agent4_input(agent4_input_path: str | None) -> dict:
    """Load agent4_input.json from the current extracted zip.

    Returns an empty dict with a warning if the file is missing.
    """
    if not agent4_input_path or not os.path.isfile(agent4_input_path):
        print(f"    ⚠ agent4_input.json not found in extracted zip: {agent4_input_path}")
        return {}
    try:
        with open(agent4_input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"    ✓ agent4_input.json loaded — {data.get('candidate_summary', {}).get('total', '?')} candidates")
        return data
    except (json.JSONDecodeError, OSError) as e:
        print(f"    ✗ Failed to load agent4_input.json at {agent4_input_path}: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# PER-MCAT PROCESSOR
# ─────────────────────────────────────────────────────────────────────────────

def process_single_mcat(mcat_row, files,
                         google_kws_all, internal_kws_all,
                         call_data_all, client, tracker, output_dir, work_dir):
    """Process one MCAT through all waves.

    Changes vs v6:
    - Loads agent4_input.json directly from the extracted zip for this MCAT.
    - Passes taxonomy_context from agent4_input.json to Agent 3.
    - Agent 4 receives agent4_input dict — NO raw CSVs.
    """
    mcat_name = mcat_row.get("glcat_mcat_name", mcat_row.get("mcat_name", "")).strip()
    mcat_id   = mcat_row.get("glcat_mcat_id",   mcat_row.get("mcat_id", "")).strip()
    mcat_url  = mcat_row.get("glcat_mcat_url",  mcat_row.get("mcat_url", "")).strip()
    thumbnail_url = mcat_row.get("thumbnail_image", "").strip()
    slug = get_mcat_slug(mcat_name)

    print(f"\n{'='*60}")
    print(f"  MCAT: {mcat_name} (ID: {mcat_id})")
    print(f"{'='*60}")

    # Filter keyword / call data for this MCAT
    google_kws = [r for r in google_kws_all
                  if r.get("MCAT ID", r.get("mcat_id", "")).strip() == mcat_id
                  or r.get("MCAT", "").strip().lower() == mcat_name.lower()]
    internal_kws = [r for r in internal_kws_all
                    if r.get("MCAT Name", r.get("mcat_name", "")).strip().lower() == mcat_name.lower()]
    call_data = [r for r in call_data_all
                 if r.get("mcat_name", "").strip().lower() == mcat_name.lower()]

    mcat_work = os.path.join(work_dir, slug)
    os.makedirs(mcat_work, exist_ok=True)

    # ── PRE-WAVE: Load agent4_input.json ──────────────────────────────────────
    print("  Pre-Wave: Loading agent4_input.json ...")
    agent4_input = load_agent4_input(files.get("agent4_input"))
    taxonomy_context = agent4_input.get("taxonomy_context", {})
    if taxonomy_context:
        print(f"    ✓ taxonomy_context loaded — full_path: {taxonomy_context.get('full_path', 'N/A')}")
    else:
        print("    ⚠ taxonomy_context is empty — Agent 3 and downstream agents will lack tree context.")

    # ── PRE-WAVE: Image Pre-loader ─────────────────────────────────────────────
    print("  Pre-Wave: Loading images ...")
    enriched_products = preload_images(
        files.get("good_products"), files.get("bad_products"),
        files.get("good_images"), files.get("bad_images"),
        mcat_id, mcat_work
    )
    print(f"    → {len(enriched_products)} products with images loaded")
    thumbnail_image = load_image_for_vision(files.get("thumbnail"))
    if thumbnail_image:
        print(f"    → Thumbnail image loaded from zip: {os.path.basename(files['thumbnail'])}")
    else:
        print("    → No thumbnail image loaded from zip")

    all_outputs = {}

    # ── WAVE 0 (sequential): Agent 1 + Agent 2 ────────────────────────────────
    print("\n  Wave 0: PDF Enricher + Product Verifier")
    all_outputs["agent1"] = run_agent_01(
        client, mcat_name, mcat_id, files.get("seller_pdfs", []), mcat_work
    )
    all_outputs["agent2"] = run_agent_02(client, mcat_name, mcat_id, enriched_products)

    # ── WAVE 1 (sequential): Agent 3 ──────────────────────────────────────────
    print("\n  Wave 1: Context Extraction + Market Research")
    all_outputs["agent3"] = run_agent_03(
        client, mcat_name, mcat_id, mcat_url,
        google_kws, internal_kws,
        all_outputs["agent1"], call_data,
        taxonomy_context=taxonomy_context,   # ← NEW in v7: pass taxonomy_context
    )
    vision_output = all_outputs["agent3"]

    # ── WAVE 2 (parallel): Agents 4-11 ────────────────────────────────────────
    print("\n  Wave 2: Parallel agents (4-11)")

    wave2_tasks = {
        # Agent 4 now receives agent4_input dict — NO raw CSVs
        "agent4": lambda: run_agent_04(
            client, mcat_name, mcat_id, vision_output, agent4_input
        ),
        "agent5": lambda: run_agent_05(
            client, mcat_name, mcat_id, vision_output, thumbnail_url, thumbnail_image
        ),
        "agent6": lambda: run_agent_06(client, mcat_name, vision_output),
        "agent7": lambda: run_agent_07(client, mcat_name, vision_output, all_outputs["agent2"]),
        "agent8": lambda: run_agent_08(client, mcat_name, vision_output),
        "agent9": lambda: run_agent_09(client, mcat_name, vision_output),
        "agent10": lambda: run_agent_10(
            client, mcat_name, mcat_id, mcat_url, vision_output, all_outputs["agent2"]
        ),
        "agent11": lambda: run_agent_11(client, mcat_name, vision_output),
    }

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_AGENTS) as pool:
        futures = {pool.submit(fn): name for name, fn in wave2_tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                all_outputs[name] = future.result()
                print(f"    ✓ {name} done")
            except Exception as e:
                print(f"    ✗ {name} failed: {e}")
                all_outputs[name] = {"error": str(e)}

    # ── WAVE 3a: Agent 12 ──────────────────────────────────────────────────────
    print("\n  Wave 3a: Name Generator")
    # slim_output now includes mcat_level and listing_count (SKILL-v7)
    agent4_slim = (
        all_outputs.get("agent4", {}).get("slim_output")
        or all_outputs.get("agent4", {}).get("related_mcats", [])
    )
    all_outputs["agent12"] = run_agent_12(
        client, mcat_name, mcat_id, vision_output, agent4_slim
    )

    # ── WAVE 3b: Agent 14 ──────────────────────────────────────────────────────
    print("\n  Wave 3b: Structural Verdict")
    all_outputs["agent14"] = run_agent_14(
        client, mcat_name, mcat_id, vision_output,
        agent4_slim,
        all_outputs.get("agent8", {}),
        all_outputs.get("agent12", {}),
    )

    # ── WAVE 4: Consolidator ───────────────────────────────────────────────────
    print("\n  Wave 4: Consolidator — Building output files")
    context_json, related_json = run_consolidator(mcat_name, mcat_id, mcat_url, all_outputs)

    # Save output files
    mcat_out = os.path.join(output_dir, slug)
    os.makedirs(mcat_out, exist_ok=True)

    ctx_path = os.path.join(mcat_out, f"{slug}_context.json")
    rel_path = os.path.join(mcat_out, f"{slug}_related_mcat_context.json")

    with open(ctx_path, "w", encoding="utf-8") as f:
        json.dump(context_json, f, indent=2, ensure_ascii=False)
    with open(rel_path, "w", encoding="utf-8") as f:
        json.dump(related_json, f, indent=2, ensure_ascii=False)

    print(f"\n  ✓ Output saved:")
    print(f"    {ctx_path}")
    print(f"    {rel_path}")

    return slug


# ─────────────────────────────────────────────────────────────────────────────
# ZIP-LEVEL RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline_for_zip(zip_name, files, output_dir, work_dir):
    """Run the full pipeline for one extracted zip (one MCAT family)."""
    tracker = TokenTracker()
    client = LLMClient(tracker)
    agent4_input_meta = load_agent4_input(files.get("agent4_input"))

    # Load shared data
    mcat_list_rows = read_csv_safe(files.get("mcat_list"))
    if not mcat_list_rows:
        print("ERROR: mcat_list.csv is empty or missing!")
        return tracker

    google_kws_all   = read_csv_safe(files.get("google_keywords"))
    internal_kws_all = read_csv_safe(files.get("internal_keywords"))
    call_data_all    = read_csv_safe(files.get("call_insights"))

    print(f"\nLoaded shared data:")
    print(f"  mcat_list: {len(mcat_list_rows)} MCATs")
    print(f"  google_kws: {len(google_kws_all)} rows")
    print(f"  internal_kws: {len(internal_kws_all)} rows")
    print(f"  call_data: {len(call_data_all)} rows")
    print(f"  seller_pdfs: {len(files.get('seller_pdfs', []))} files")
    if files.get("agent4_input"):
        print(f"  agent4_input: {os.path.abspath(files['agent4_input'])}")
    else:
        print("  agent4_input: ✗ not found")

    if google_kws_all:
        print(f"  google_kws columns: {list(google_kws_all[0].keys())}")
    if internal_kws_all:
        print(f"  internal_kws columns: {list(internal_kws_all[0].keys())}")

    root_mcat_id = str(agent4_input_meta.get("root_mcat_id", "")).strip()
    root_mcat_name = str(agent4_input_meta.get("root_mcat_name", "")).strip().lower()

    # Filter to the MCAT identified by the in-zip agent4_input.json when possible.
    target_rows = []
    if root_mcat_id or root_mcat_name:
        target_rows = [
            r for r in mcat_list_rows
            if (
                root_mcat_id
                and str(r.get("glcat_mcat_id", r.get("mcat_id", ""))).strip() == root_mcat_id
            ) or (
                root_mcat_name
                and (r.get("glcat_mcat_name", r.get("mcat_name", ""))).strip().lower() == root_mcat_name
            )
        ]
        if target_rows:
            print("  Target MCAT resolved from agent4_input.json")

    # Fallback to zip-name matching if agent4_input.json lacks usable root metadata.
    if not target_rows:
        target_rows = [r for r in mcat_list_rows
                       if (r.get("glcat_mcat_name", r.get("mcat_name", ""))
                           .strip().lower() == zip_name.lower())]
    if not target_rows:
        print(f"  WARNING: No MCAT matched zip name '{zip_name}'. Processing all {len(mcat_list_rows)}.")
        target_rows = mcat_list_rows

    # Process each MCAT
    total = len(target_rows)
    for i, mcat_row in enumerate(target_rows):
        mcat_name = (mcat_row.get("glcat_mcat_name", mcat_row.get("mcat_name", ""))).strip()
        if not mcat_name:
            print(f"\n  Skipping row {i+1}: empty mcat_name")
            continue

        print(f"\n{'#'*60}")
        print(f"  Processing MCAT {i+1}/{total}: {mcat_name}")
        print(f"{'#'*60}")

        try:
            process_single_mcat(
                mcat_row, files,
                google_kws_all, internal_kws_all,
                call_data_all, client, tracker, output_dir, work_dir,
            )
        except Exception as e:
            print(f"\n  ✗✗ MCAT '{mcat_name}' FAILED: {e}")
            import traceback
            traceback.print_exc()
            continue

    # Save token report
    report_path = os.path.join(output_dir, "token_usage_report.json")
    tracker.save_report(report_path)
    tracker.print_summary()
    print(f"\nToken report saved: {report_path}")

    return tracker
