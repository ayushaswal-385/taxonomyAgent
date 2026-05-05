"""Wave 2 agents (parallel): Agents 4-11. All consume Agent 3 output."""
import json


# ─────────────────────────────────────────────────────────────────────────────
# AGENT 4 — MCAT Relationship Mapper
# ─────────────────────────────────────────────────────────────────────────────

def run_agent_04(client, mcat_name, mcat_id, vision_output, agent4_input):
    """Agent 4 — MCAT Relationship Mapper.

    Inputs:
      vision_output  — Agent 3 output (includes taxonomy_context).
      agent4_input   — Pre-built dict from agent4_input.json (from catalogue_preprocessor.py).
                       Contains: taxonomy_context, candidates[], family_context_pairs[],
                       candidate_summary, root_mcat_id, root_mcat_name.

    The candidate pool, overlap_data, mcat_level, listing_count, and family_context_pairs
    are fully pre-assembled. Agent 4 does NOT read any raw CSV files.

    Mandatory Page-Browse Rule (enforced in prompt — NOT for pure semantic-only candidates):
      For any candidate with ≥200 products OR ≥100 suppliers: web_fetch that MCAT's
      IndiaMART page before finalising is_duplicate. Answer:
        1. Visual equivalence — same physical product as root?
        2. Spec equivalence — spec snippets overlap substantially?
        3. IndiaMART cross-reference — root shown as related link on this page?
    """
    # Pull key data from agent4_input
    candidates = agent4_input.get("candidates", [])
    family_context_pairs = agent4_input.get("family_context_pairs", [])
    candidate_summary = agent4_input.get("candidate_summary", {})
    taxonomy_ctx = agent4_input.get("taxonomy_context", {})

    # Page-browse for Agent 4 is DISABLED (hard shutoff — too slow).
    page_browse_required = []

    # Vision context (slim — only what Agent 4 needs from Agent 3)
    vision_summary = {}
    if vision_output and isinstance(vision_output, dict):
        vision_summary = {k: v for k, v in vision_output.items()
                         if k in ["mcat_description", "listing_quality", "alt_names", "market_context"]}

    system = f"""You are Agent 4 — MCAT Relationship Mapper for "{mcat_name}" (ID: {mcat_id}).

=== ROLE ===
Classify every candidate in the pre-built pool. Do NOT read any raw CSV files.
All candidate data, overlap metrics, mcat_level, listing_count, and family_context_pairs
are already assembled in the inputs below.

=== STEPS ===

Step 1 — Read the pre-built candidate pool (provided in user message).
  Each candidate has: mcat_id, mcat_name, mcat_level, listing_count, source_flags,
  source_tier_primary, pre_relevance, pre_relationship, similarity_score, pre_note,
  overlap_data (null → set all overlap fields to 0 in output).

  Use mcat_level to resolve relationship with certainty:
  - Candidate level < root level → parent_category or super_parent
  - Candidate level = root level → sibling_category (or brand/cross_sell etc.)
  - Candidate level > root level → child (could be cross_sell/accessory/unrelated)

Step 2 — Build family_context_note per candidate.
  Read family_context_pairs (sibling-to-sibling overlap). For each candidate, write
  1 sentence summarising how it relates to other family members. No new candidates added.

Step 3 — Classify each candidate:
  3a. relationship (12-value enum):
      super_parent | parent_category | sibling_category | brand_mcat | cross_sell |
      upsell | downsell | accessory | parts | service | substitute | unrelated
      → Buyer-perspective first, validated by overlap data.
      → High product overlap (>15% from root's side) + same buyer intent → sibling or parent.

  3b. sibling_bifurcation_type (when relationship=sibling_category):
      material | brand | technology | application | condition | form_factor |
      capacity_size | fuel_energy | segment | specification | output_type |
      geographic | composite | null

  3c. Duplicate / merge flags: is_duplicate, to_be_merged, is_overlapping
      Apply merge signals S1–S6.

  3d. Category Nature (6 dimensions per candidate):
      is_generic, is_specific, is_vague, is_thin, is_branded, is_service


=== OVERRIDE RULE A — Brand MCAT Protection ===
Brand MCAT (name anchored to single commercial brand):
  is_brand_mcat: yes, is_duplicate: no, to_be_merged: no, is_overlapping: yes,
  relationship: sibling_category
  routing_note MUST start: "BRAND MCAT — do NOT absorb, do NOT mark as duplicate."
  Never in structural_verdict.mcats_to_absorb.

=== OVERRIDE RULE B — Parent Direct-Match Check ===
Test: "Is the parent MCAT name just a longer/more formal way of saying the same thing as root?"
  YES → is_duplicate: yes, to_be_merged: yes (root merges INTO parent as canonical)
  NO  → is_duplicate: no, to_be_merged: no

=== SEGMENT ISOLATION RULE ===
When Agent 3 flags needs_cleaning: yes:
  Identify candidates belonging to the contaminating segment → relationship: unrelated
  OMIT all unrelated candidates from your output entirely (do NOT include them in related_mcats or slim_output).

=== OUTPUT ===
IMPORTANT: Candidates classified as relationship="unrelated" must be EXCLUDED from both
related_mcats and slim_output. Do NOT include them in the JSON at all.

RESPOND WITH ONLY VALID JSON:
{{
  "related_mcats": [
    {{
      "mcat_name": "",
      "mcat_id": "",
      "mcat_level": null,
      "listing_count": null,
      "source_flags": [],
      "source_tier_primary": "",
      "is_brand_mcat": "yes|no",
      "relationship": "<12-value enum>",
      "sibling_bifurcation_type": "<enum>|null",
      "direction": "bidirectional|from_this|from_that_into_this",
      "reason": ["bullet 1", "bullet 2"],
      "is_duplicate": "yes|no",
      "to_be_merged": "yes|no",
      "is_overlapping": "yes|no",
      "overlap_with_root": {{
        "common_products": 0,
        "common_suppliers": 0,
        "product_overlap_pct_root": 0.0,
        "product_overlap_pct_candidate": 0.0,
        "supplier_overlap_pct_root": 0.0,
        "supplier_overlap_pct_candidate": 0.0
      }},
      "total_products": 0,
      "total_suppliers": 0,
      "merge_signals_fired": [],
      "category_nature": {{
        "is_generic": "yes|no",
        "is_specific": "yes|no",
        "is_vague": "yes|no",
        "is_thin": "yes|no",
        "is_branded": "yes|no",
        "is_service": "yes|no",
        "reason": "2-bullet"
      }},
      "family_context_note": "1 sentence on relationship to other family members",
      "routing_note": "",
      "page_browse_performed": false,
      "page_browse_check": null
    }}
  ],
  "slim_output": [
    {{
      "mcat_name": "",
      "mcat_id": "",
      "mcat_level": null,
      "listing_count": null,
      "relationship": "",
      "sibling_bifurcation_type": "",
      "is_duplicate": "",
      "to_be_merged": "",
      "is_brand_mcat": "",
      "merge_signals_fired": [],
      "category_nature_is_thin": "",
      "category_nature_is_vague": "",
      "source_flags": []
    }}
  ]
}}"""

    # Serialise inputs for user message
    candidates_text = json.dumps(candidates, indent=1)
    fcp_text = json.dumps(family_context_pairs[:50], indent=1) if family_context_pairs else "[]"
    page_browse_text = json.dumps(page_browse_required, indent=1) if page_browse_required else "[]"
    taxonomy_text = json.dumps(taxonomy_ctx, indent=1)
    vision_text = json.dumps(vision_summary, indent=1)
    summary_text = json.dumps(candidate_summary, indent=1)

    user = f"""Root MCAT: {mcat_name} (ID: {mcat_id})

=== TAXONOMY CONTEXT ===
{taxonomy_text}

=== CANDIDATE SUMMARY ===
{summary_text}

=== AGENT 3 CONTEXT (listing_quality, mcat_description) ===
{vision_text}

=== PRE-BUILT CANDIDATE POOL (classify ALL — {len(candidates)} candidates) ===
{candidates_text}

=== FAMILY CONTEXT PAIRS (sibling-to-sibling overlap — for family_context_note only) ===
{fcp_text}

Instructions:
1. Classify EVERY candidate in the pool above.
2. EXCLUDE any candidate whose final relationship is "unrelated" — do NOT add it to related_mcats or slim_output.
3. Set slim_output as a condensed copy (one entry per non-unrelated related_mcat) for Agent 12 and Agent 14.
4. Where overlap_data is null on a candidate: set all overlap fields to 0 in your output.
5. Set page_browse_performed: false and page_browse_check: null for all candidates."""

    result = client.call("Agent_04_Mapper", mcat_name, system, user, max_tokens=120000)
    content = result.get("content", {})
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            content = {}

    # ── Post-process: strip any unrelated entries that slipped through ────────
    if isinstance(content, dict):
        related = content.get("related_mcats", [])
        if isinstance(related, list):
            filtered = [m for m in related if m.get("relationship") != "unrelated"]
            dropped = len(related) - len(filtered)
            if dropped:
                print(f"    [Agent4] Stripped {dropped} unrelated candidate(s) from related_mcats.")
            content["related_mcats"] = filtered

        slim = content.get("slim_output", [])
        if isinstance(slim, list):
            filtered_slim = [m for m in slim if m.get("relationship") != "unrelated"]
            dropped_slim = len(slim) - len(filtered_slim)
            if dropped_slim:
                print(f"    [Agent4] Stripped {dropped_slim} unrelated candidate(s) from slim_output.")
            content["slim_output"] = filtered_slim

    return content


# ─────────────────────────────────────────────────────────────────────────────
# AGENT 5 — Name + Image Audit
# ─────────────────────────────────────────────────────────────────────────────

def run_agent_05(client, mcat_name, mcat_id, vision_output, thumbnail_url):
    """Agent 5 — Name + Image Audit."""
    system = f"""You are Agent 5 — Name + Image Audit for "{mcat_name}".
Evaluate the current MCAT name and thumbnail. Produce 3 AI thumbnail image descriptions.

Name Audit: Cross-reference name against keywords, Amazon, Google Shopping.
Thumbnail Audit: current_thumbnail_correct: false ONLY if wrong product shown, brochure instead of product, no product visible, or seller watermark obstruction.

When listing_quality.needs_cleaning=yes, ALL 3 thumbnail suggestions MUST represent primary_segment ONLY.

RESPOND WITH ONLY VALID JSON:
{{"mcat_name_audit":{{"verdict":"correct|needs_improvement|incorrect","reason":"","suggested_name":null}},
"mcat_image":{{"quality":"good|acceptable|poor","correctness":"correct|incorrect","issues":[]}},
"thumbnail_audit":{{"current_thumbnail_correct":true,"reason":["bullet1","bullet2"]}},
"mcat_image_suggestions":[{{"id":1,"description":"","rationale":"max 2 sentences","prompt_for_generation":"","watermark":{{"position":"bottom-right","text":"IndiaMART AI","applied":true}}}}]}}"""

    vis = json.dumps({k: v for k, v in vision_output.items()
                      if k in ["mcat_description", "listing_quality", "alt_names",
                                "top_internal_keywords", "top_google_keywords",
                                "market_context", "thumbnail_image_description"]},
                     indent=1) if vision_output else "{}"
    user = f"MCAT: {mcat_name}\nThumbnail URL: {thumbnail_url}\n\nAgent 3 Context:\n{vis}"
    result = client.call("Agent_05_NameImage", mcat_name, system, user, max_tokens=4000)
    return result.get("content", {})


# ─────────────────────────────────────────────────────────────────────────────
# AGENT 6 — Buyer Display Importance
# ─────────────────────────────────────────────────────────────────────────────

def run_agent_06(client, mcat_name, vision_output):
    """Agent 6 — Buyer Display Importance."""
    system = f"""You are Agent 6 — Buyer Display Importance for "{mcat_name}".
Determine which display signals matter most to buyers. Output becomes gating_flags.

Unit Decision: 3 steps:
1. Research how sellers actually quote
2. Model the actual buyer-seller interaction
3. Check for sub-segments with different units

unit_important: High = unit is variable, mismatch breaks price comparability. Low = universally fixed.
buyer_attracting_attributes: What makes a buyer pick THIS listing over others?

RESPOND WITH ONLY VALID JSON:
{{"price_important":"High|Medium|Low","price_reason":"2-bullet",
"image_important":"High|Medium|Low","image_reason":"",
"unit_important":"High|Low","recommended_unit":"","unit_reasoning_source":"","unit_note":"",
"specification_important":"High|Medium|Low","show_on_listing":true,"buyer_attracting_attributes":["attr1","attr2"],
"spec_reason":"2-bullet"}}"""

    vis = json.dumps({k: v for k, v in vision_output.items()
                      if k in ["mcat_description", "price_range", "market_context",
                                "raw_listings"]}, indent=1) if vision_output else "{}"
    user = f"MCAT: {mcat_name}\n\nAgent 3 Context:\n{vis}"
    result = client.call("Agent_06_Buyer", mcat_name, system, user, max_tokens=3000)
    return result.get("content", {})


# ─────────────────────────────────────────────────────────────────────────────
# AGENT 7 — Listing Image Type + Photo Examples
# ─────────────────────────────────────────────────────────────────────────────

def run_agent_07(client, mcat_name, vision_output, agent2_output):
    """Agent 7 — Listing Image Type + Photo Examples."""
    system = f"""You are Agent 7 — Listing Image Type Classifier + Photo Examples for "{mcat_name}".
Two responsibilities:
1. Classify listing image type: object_only (OCR cannot extract useful text) or object_with_info (OCR can extract meaningful info)
2. Produce 10 relevant and 10 irrelevant photo examples from provided data

Source priority for relevant: Agent 2 verified_good > Agent 3 raw_images > web search
Source priority for irrelevant: Agent 2 verified_bad > page browse wrong products

NO INVENTED URLs. Every URL must come from provided data.

RESPOND WITH ONLY VALID JSON:
{{"image_type_recommendation":{{"type":"object_only|object_with_info","reason":"","ocr_useful":false}},
"relevant_photos":{{"summary":"one sentence","product_identity":[],"acceptable_scenes":[],"examples":[{{"photo_url":"","listing_title":"","item_id":"","reason":"","source":"verified_good|page_browse_only"}}]}},
"irrelevant_photos":{{"summary":"","failure_classes":[{{"class":"","description":"","examples":[],"detection_signal":"","failure_mode":"","action":""}}]}},
"thin_photos":{{"summary":"","thinness_signals":[],"examples":[]}},
"photo_count_note":"",
"input_data_absent":false}}"""

    raw_images = json.dumps(vision_output.get("raw_images", [])[:15], indent=1) if vision_output else "[]"
    a2_good = json.dumps(agent2_output.get("verified_good_image_urls", [])[:15]) if agent2_output else "[]"
    a2_bad = json.dumps(agent2_output.get("verified_bad_image_urls", [])[:15]) if agent2_output else "[]"
    absent = agent2_output.get("input_data_absent", True) if agent2_output else True

    user = f"""MCAT: {mcat_name}
Agent 2 input_data_absent: {absent}
Agent 2 verified good image URLs: {a2_good}
Agent 2 verified bad image URLs: {a2_bad}
Agent 3 raw_images: {raw_images}
Agent 3 mcat_description: {json.dumps(vision_output.get('mcat_description', {}), indent=1)}"""

    result = client.call("Agent_07_ImageType", mcat_name, system, user, max_tokens=5000)
    return result.get("content", {})


# ─────────────────────────────────────────────────────────────────────────────
# AGENT 8 — Category Nature
# ─────────────────────────────────────────────────────────────────────────────

def run_agent_08(client, mcat_name, vision_output):
    """Agent 8 — Category Nature."""
    system = f"""You are Agent 8 — Category Nature for "{mcat_name}".
Classify across 6 independent boolean dimensions:
- is_generic: High-volume broad catch-all (yes) vs specific bounded (no)
- is_specific: Well-scoped clear buyer intent (yes) vs broad diffuse (no)
- is_vague: Ambiguous name mixed intents (yes) vs clear unambiguous (no)
- is_thin: Insufficient volume to stand alone (yes) vs sufficient (no)
- is_branded: Anchored to brand/trademark (yes) vs generic (no)
- is_service: Service offering (yes) vs physical product (no)

Use taxonomy_context.listing_count as a hard anchor for is_thin — do NOT estimate from page tiles.
A deep-level MCAT (level 5+) classified is_generic:yes is almost certainly wrong — flag for review.

RESPOND WITH ONLY VALID JSON:
{{"is_generic":"yes|no","is_specific":"yes|no","is_vague":"yes|no","is_thin":"yes|no","is_branded":"yes|no","is_service":"yes|no","reason":"2-bullet justification"}}"""

    # Include taxonomy_context for hard anchors
    tc = vision_output.get("taxonomy_context", {}) if vision_output else {}
    vis = json.dumps({k: v for k, v in vision_output.items()
                      if k in ["mcat_description", "listing_quality", "price_range",
                                "taxonomy_context"]}, indent=1) if vision_output else "{}"
    user = f"MCAT: {mcat_name}\n\nAgent 3 Context (includes taxonomy_context):\n{vis}"
    result = client.call("Agent_08_Nature", mcat_name, system, user, max_tokens=1500)
    return result.get("content", {})


# ─────────────────────────────────────────────────────────────────────────────
# AGENT 9 — Listing Governance
# ─────────────────────────────────────────────────────────────────────────────

def run_agent_09(client, mcat_name, vision_output):
    """Agent 9 — Listing Governance."""
    system = f"""You are Agent 9 — Listing Governance for "{mcat_name}".
Determine:
- location_exception: true ONLY when location is a genuine buyer decision factor (GI-tagged, regional origin). NOT for industrial machinery.
- biz_exception: true ONLY when business type is a genuine buyer filter ("Authorised Dealer" where OEM vs reseller matters).

RESPOND WITH ONLY VALID JSON:
{{"location_exception":false,"location_exception_reason":"","biz_exception":false,"biz_exception_reason":""}}"""

    vis = json.dumps({k: v for k, v in vision_output.items()
                      if k in ["mcat_description", "market_context"]}, indent=1) if vision_output else "{}"
    user = f"MCAT: {mcat_name}\n\nAgent 3 Context:\n{vis}"
    result = client.call("Agent_09_Governance", mcat_name, system, user, max_tokens=1500)
    return result.get("content", {})


# ─────────────────────────────────────────────────────────────────────────────
# AGENT 10 — Listing Examples Extractor
# ─────────────────────────────────────────────────────────────────────────────

def run_agent_10(client, mcat_name, mcat_id, mcat_url, vision_output, agent2_output):
    """Agent 10 — Listing Examples Extractor."""
    system = f"""You are Agent 10 — Listing Examples Extractor for "{mcat_name}".
Select 5 extreme-good + 5 extreme-bad listing examples from REAL data provided.

NO FABRICATION. Use only listings from the provided data.
Extreme good = passes ALL signals with ≥3 buyer-attracting attributes
Extreme bad = actively wrong content, fails ≥2 signals or catastrophic violation. NOT merely thin/incomplete.

verdict enum: correct|incorrect|incorrect_title|incorrect_specs
outlier _reason must identify a WRONG THING PRESENT, never a missing thing.

Build wrong_mcat_classifier from incorrect examples — every class names a specific target MCAT.

RESPOND WITH ONLY VALID JSON:
{{"good_listings":[{{"title":"","price":"","specs":"","image_url":"","proddetail_url":"","verdict":"correct","why_good":"","source":"verified_good|page_browse"}}],
"bad_listings":[{{"title":"","price":"","specs":"","image_url":"","proddetail_url":"","verdict":"incorrect","failure_reason":"","correct_mcat":"","source":"verified_bad|page_browse"}}],
"relevant_titles":{{"summary":"","strong_positive_signals":[],"structural_patterns":[],"examples":{{"extreme_good":[],"acceptable":[]}}}},
"thin_titles":{{"summary":"","thinness_signals":[],"examples":[]}},
"irrelevant_titles":{{"summary":"","failure_classes":[{{"class":"","signal":"","failure_mode":"","rule":"","examples":[]}}]}},
"wrong_mcat_classifier":{{"description":"","input_data_absent":false,"classes":[{{"class":"","signal":"","examples":[],"correct_mcat":""}}]}},
"few_shot_examples":[]}}"""

    raw_listings = json.dumps(vision_output.get("raw_listings", [])[:20], indent=1) if vision_output else "[]"
    a2_good = json.dumps(agent2_output.get("verified_good_products", [])[:10], indent=1) if agent2_output else "[]"
    a2_bad = json.dumps(agent2_output.get("verified_bad_products", [])[:10], indent=1) if agent2_output else "[]"
    absent = agent2_output.get("input_data_absent", True) if agent2_output else True

    user = f"""MCAT: {mcat_name} (ID: {mcat_id})
Page URL: {mcat_url}
Agent 2 input_data_absent: {absent}
MCAT description: {json.dumps(vision_output.get('mcat_description', {}), indent=1)}

Agent 2 Verified Good Products:
{a2_good}

Agent 2 Verified Bad Products:
{a2_bad}

Agent 3 Raw Listings from Page:
{raw_listings}

Select 5 extreme good + 5 extreme bad examples from the data above. Build the wrong_mcat_classifier and few_shot_examples."""

    result = client.call("Agent_10_Examples", mcat_name, system, user, max_tokens=18000)
    return result.get("content", {})


# ─────────────────────────────────────────────────────────────────────────────
# AGENT 11 — Company Importance Classifier
# ─────────────────────────────────────────────────────────────────────────────

def run_agent_11(client, mcat_name, vision_output):
    """Agent 11 — Company Importance Classifier."""
    system = f"""You are Agent 11 — Company Importance Classifier for "{mcat_name}".
Determine how important company/brand identity is for buyers.

company_important: High (brand materially affects trust), Medium (brands exist but unbranded market too), Low (brand not meaningful)
brand_in_title: relevant (helps identify genuine) or contamination (false claim)
trademark_risk: yes/no (known counterfeit/brand hijacking?)
authorised_dealer_brand_exception: yes/no

RESPOND WITH ONLY VALID JSON:
{{"company_important":"High|Medium|Low","importance_driver":"","brand_in_title":"relevant|contamination","brand_in_title_reason":"","trademark_risk":"yes|no","trademark_risk_note":"","authorised_dealer_brand_exception":"yes|no","authorised_dealer_reason":""}}"""

    vis = json.dumps({k: v for k, v in vision_output.items()
                      if k in ["mcat_description", "market_context", "raw_listings"]},
                     indent=1) if vision_output else "{}"
    user = f"MCAT: {mcat_name}\n\nAgent 3 Context:\n{vis}"
    result = client.call("Agent_11_Company", mcat_name, system, user, max_tokens=2000)
    return result.get("content", {})
