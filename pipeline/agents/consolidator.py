"""Consolidator — Two-File Builder (Wave 4). Assembles all agent outputs into context.json and related_mcat_context.json."""
import json
from datetime import date
from pipeline.file_resolver import get_mcat_slug

def run_consolidator(mcat_name, mcat_id, mcat_url, all_outputs):
    """Assemble all agent outputs into two deliverable JSON files."""
    a1 = all_outputs.get("agent1", {}) or {}
    a2 = all_outputs.get("agent2", {}) or {}
    a3 = all_outputs.get("agent3", {}) or {}
    a4 = all_outputs.get("agent4", {}) or {}
    a5 = all_outputs.get("agent5", {}) or {}
    a6 = all_outputs.get("agent6", {}) or {}
    a7 = all_outputs.get("agent7", {}) or {}
    a8 = all_outputs.get("agent8", {}) or {}
    a9 = all_outputs.get("agent9", {}) or {}
    a10 = all_outputs.get("agent10", {}) or {}
    a11 = all_outputs.get("agent11", {}) or {}
    a12 = all_outputs.get("agent12", {}) or {}
    a14 = all_outputs.get("agent14", {}) or {}
    today = date.today().isoformat()

    # ── data_quality_flags ──
    dqf = None
    affected = []
    if a2.get("input_data_absent"):
        affected.extend(["relevant_photos", "irrelevant_photos", "few_shot_examples.good_listings", "few_shot_examples.bad_listings", "wrong_mcat_classifier"])
    if a7.get("input_data_absent"):
        if "relevant_photos" not in affected: affected.append("relevant_photos")
    if affected:
        dqf = {"input_data_absent": True, "affected_fields": affected}

    # ── gating_flags ──
    gating = {
        "use_photo": True, "use_specs": True,
        "photo_weight": "HIGH" if a6.get("image_important") == "High" else ("MEDIUM" if a6.get("image_important") == "Medium" else "LOW"),
        "isq_important": a6.get("specification_important", "Medium"),
        "company_important": a11.get("company_important", "Low"),
        "price_important": a6.get("price_important", "Medium"),
        "unit_important": a6.get("unit_important", "Low"),
        "canonical_unit": a6.get("recommended_unit", "per piece"),
        "canonical_unit_note": a6.get("unit_note", ""),
        "hyperlocal": "All India",
        "biz_exception": a9.get("biz_exception", False),
        "location_exception": a9.get("location_exception", False),
        "ocr": a7.get("image_type_recommendation", {}).get("ocr_useful", False) if isinstance(a7.get("image_type_recommendation"), dict) else False,
        "ocr_note": a7.get("image_type_recommendation", {}).get("reason", "") if isinstance(a7.get("image_type_recommendation"), dict) else "",
        "buyer_attracting_attributes": a6.get("buyer_attracting_attributes", []),
        "show_spec_on_listing": a6.get("show_on_listing", True),
        "reason": "",
    }

    # ── names_aliases ──
    names = {
        "canonical": mcat_name,
        "enhanced_names": {
            "4w": a12.get("enhanced_name_4w", ""),
            "5w": a12.get("enhanced_name_5w", ""),
            "6w": a12.get("enhanced_name_6w", ""),
            "long": a12.get("enhanced_name_long", ""),
        },
        "aliases": a12.get("top_10_alt_names", a3.get("alt_names", [])),
        "segment_contamination_disclaimer": a12.get("segment_contamination_disclaimer"),
        "search_queries": [],
    }

    # ── structural_verdict ──
    sv = dict(a14) if a14 else {}
    sv["thumbnail_audit"] = a5.get("thumbnail_audit", {"current_thumbnail_correct": True, "reason": []})

    # ── related_mcats_summary (lean index) — unrelated excluded ──
    related_summary = []
    for rm in a4.get("related_mcats", a4.get("slim_output", [])):
        if rm.get("relationship") == "unrelated":
            continue
        related_summary.append({
            "mcat_name": rm.get("mcat_name", ""),
            "relationship": rm.get("relationship", "unknown"),
            "is_duplicate": rm.get("is_duplicate", "no"),
        })

    # ── Build context.json ──
    context = {
        "mcat_id": int(mcat_id) if str(mcat_id).isdigit() else mcat_id,
        "mcat_name": mcat_name,
        "version": "1.0",
        "generated": today,
        "pipeline_version": "v5.9",
        "page_url": mcat_url or "",
    }
    if dqf:
        context["data_quality_flags"] = dqf
    
    context["mcat_description"] = a3.get("mcat_description", {"short": "", "long": "", "product_types": [], "primary_applications": [], "buyer_segments": []})
    context["gating_flags"] = gating
    context["category_nature"] = a8 if isinstance(a8, dict) and "is_generic" in a8 else {"is_generic": "no", "is_specific": "yes", "is_vague": "no", "is_thin": "no", "is_branded": "no", "is_service": "no", "reason": ""}
    context["structural_verdict"] = sv
    context["names_aliases"] = names
    context["relevant_photos"] = a7.get("relevant_photos", {"summary": "", "product_identity": [], "acceptable_scenes": [], "examples": []})
    context["thin_photos"] = a7.get("thin_photos", {"summary": "", "thinness_signals": [], "examples": []})
    context["irrelevant_photos"] = a7.get("irrelevant_photos", {"summary": "", "failure_classes": []})
    context["relevant_titles"] = a10.get("relevant_titles", {"summary": "", "strong_positive_signals": [], "structural_patterns": [], "examples": {"extreme_good": [], "acceptable": []}})
    context["thin_titles"] = a10.get("thin_titles", {"summary": "", "thinness_signals": [], "examples": []})
    context["irrelevant_titles"] = a10.get("irrelevant_titles", {"summary": "", "failure_classes": []})
    context["wrong_mcat_classifier"] = a10.get("wrong_mcat_classifier", {"description": "", "input_data_absent": False, "classes": []})
    context["few_shot_examples"] = a10.get("few_shot_examples", [])
    context["mcat_thumbnail_images"] = a5.get("mcat_image_suggestions", [])
    context["related_mcats_summary"] = related_summary
    context["missing_data_fallbacks"] = []
    
    pdf_summary = a1.get("pdf_summary") if a1 else None
    context["seller_pdfs"] = {
        "pdf_count_processed": pdf_summary.get("pdf_count_processed", 0) if pdf_summary else 0,
        "agent1_pdf_supplement": pdf_summary.get("agent1_pdf_supplement", []) if pdf_summary else [],
    }
    context["buyleads"] = None

    # ── Build related_mcat_context.json ──
    related_context = {
        "mcat_id": int(mcat_id) if str(mcat_id).isdigit() else mcat_id,
        "mcat_name": mcat_name,
        "generated": today,
        "pipeline_version": "v5.9",
        "page_url": mcat_url or "",
        "file_purpose": "Taxonomy governance — related MCAT classification, overlap data, and merge analysis.",
        "related_mcats": [m for m in a4.get("related_mcats", [])
                          if m.get("relationship") != "unrelated"],
        "merge_summary": {
            "absorb_others_into_this": sv.get("absorb_others_into_this", "no"),
            "mcats_to_absorb": sv.get("mcats_to_absorb", []),
            "merge_into_other": sv.get("merge_into_other", "no"),
            "merge_into_other_target": sv.get("merge_into_other_target"),
        },
        "alias_collision_merge_signals": a12.get("alias_collision_merge_signals", []),
    }

    return context, related_context
