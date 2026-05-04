---
name: mcat-taxonomy-pipeline-v5.9
description: >
  Multi-agent orchestration pipeline that builds two output files per MCAT:
  (1) context.json — the primary listing audit AI knowledge base, and
  (2) related_mcat_context.json — the taxonomy governance file for this MCAT.
  Use this skill whenever the user wants to analyse, enrich, clean, or audit an MCAT,
  assess brand/company importance, determine whether an MCAT should be dissolved/renamed/merged,
  produce ready-to-deploy AI context files for listing audit at scale, run a product taxonomy
  audit, generate SEO-optimised category names, evaluate buyer display importance, classify
  category nature, recommend listing image types, audit listing governance, check listing page
  quality, classify related MCATs using internal overlap data, or generate AI thumbnail images.
  Trigger on: "MCAT", "category audit", "taxonomy pipeline", "context file", "listing audit",
  "category enrichment", "product classification", "listing examples", "brand importance",
  "related categories", "should I dissolve", "should I merge", "should I rename",
  "pre-cleaning", "structural verdict", "senior category manager knowledge".
---

# MCAT Taxonomy Pipeline v5.9 — Complete Skill Reference

This is the master reference document. For API production use, load the skill in chunks:
- `skill_pipeline_context.md` as system[0] (cached, always identical)
- `skill_agent_XX.md` as system[1] (cached per agent type)
- Variable MCAT data only in the user message

---

## Pipeline Overview

A 14-agent orchestration pipeline that processes **one MCAT at a time** and produces two output files:

1. **`{slug}_context.json`** — the listing audit AI knowledge base. Contains everything needed to audit individual listings at scale: photo rules, title rules, wrong-MCAT classifier, few-shot examples, gating flags, names/aliases, and structural verdict. Loaded at audit time.

2. **`{slug}_related_mcat_context.json`** — the taxonomy governance file. Contains the full related MCAT classification table with buyer journey mapping, overlap data, category nature tags, and merge signal analysis. Used by taxonomy and category management teams.

**Why two files:** Separating related MCATs into a dedicated governance file keeps `context.json` lean and focused on the listing audit task. The audit AI does not need full overlap tables at inference time.

**The core idea:** Give the AI everything a senior Category Manager knows about a category — what a good listing looks like, what a bad one looks like, which MCATs to route wrong listings to — and let it audit every listing the same way, every time, at scale.

**Execution model:** One MCAT at a time. The orchestrator iterates `mcat_list.csv` row by row. All waves complete for MCAT N before MCAT N+1 begins. This eliminates cross-MCAT context bleed.

All agent outputs are intermediate — consumed by the Consolidator only. The two JSON files are the only deliverables per MCAT run.

---

## All reason/analysis/justification fields across EVERY agent: max 2–3 concise bullet points.
No paragraphs. Each bullet = one evidence-backed sentence.

---

## Architecture

```
Per-MCAT loop ─────────────────────────────────────────────────────────
  Pre-Wave (sequential — runs before any agent for THIS MCAT):
    Preprocessor — catalogue_preprocessor.py
                   Inputs: all_mcats_indiamart.csv + root mcat_name + root mcat_id
                   Output: preprocessed_candidates.csv (scored candidate list for THIS MCAT only)
                   Zero token cost — pure Python, no API calls.

    Image Pre-loader — orchestrator responsibility (pure Python, no API calls)
                   Inputs:
                     - good_products.csv rows for THIS MCAT (item_id + product_page_url)
                     - bad_products.csv rows for THIS MCAT (item_id + product_page_url)
                     - good_images.zip — images named {fk_pc_item_id}.jpeg/.jpg/.png
                     - bad_images.zip  — images named {fk_pc_item_id}.jpeg/.jpg/.png
                   Processing:
                     1. Unzip both zip files into temp directories
                     2. For each CSV row: match item_id to image file in the corresponding
                        zip by filename (e.g. 184233462.jpeg)
                     3. Convert matched image to base64
                     4. If no matching image file found in zip: set image_base64: null,
                        image_status: "missing_from_zip"
                   Output: enriched_products list passed directly to Agent 2
                   Schema per item:
                     { item_id, ai_label, image_url, image_base64, image_mime_type,
                       image_status, product_page_url }
                   image_status enum: "ok" | "missing_from_zip"
                   Raw CSV rows are NEVER passed to Agent 2 — always the enriched list.

  Wave 0 (sequential):
    Agent 1  — PDF Enricher
               Inputs: up to 5 seller PDFs for THIS MCAT + mcat_name (Target Category)
               Each PDF extracted independently → 5 JSONs merged → filtered to
               "Identified for input category" only → passed to Agent 3
    Agent 2  — Product & Image Verifier
               Inputs: enriched_products list from Image Pre-loader (base64 images included)
               Analyses pre-loaded image (visual) + fetches product page (text) per item
               Verifies/overrides AI label → resolves conflicts
               Outputs verified_good + verified_bad lists to Agents 7 & 10

  Wave 1 (sequential):
    Agent 3  — Context Extraction + Market Research + Listing Quality Check
               Inputs: page URL, google KWs, internal KWs,
                       Agent 1 filtered PDF data (supplement — identified category only),
                       seller_buyer_call_data for this MCAT (supplement)

  Wave 2 (parallel — all consume Agent 3 vision_output):
    Agent 4  — MCAT Relationship Mapper
               Inputs: existing_related_mcats (File 1 — to AUDIT, not trust),
                       related_mcats_overlap ALL pairs incl. non-root (File 2, family context),
                       preprocessed_candidates for THIS MCAT (Preprocessor output),
                       mcat_list.csv (safety net — union any missing MCATs into candidate pool)
    Agent 5  — Name + Image Audit            (+ thumbnail_image_url)
    Agent 6  — Buyer Display Importance
    Agent 7  — Listing Image Type + Photo Examples
               (good_products + bad_products if provided; fallback: page_browse_only)
    Agent 8  — Category Nature
    Agent 9  — Listing Governance
    Agent 10 — Listing Examples Extractor    (mandatory web_fetch of real listings)
    Agent 11 — Company Importance Classifier

  Wave 3a (sequential — must complete before Wave 3b):
    Agent 12 — Name Generator
               Produces alias_collision_merge_signals → consumed by Agent 14

  Wave 3b (sequential):
    Agent 14 — Pre-Cleaning Structural Verdict

  Wave 4 (sequential):
    Consolidator — Two-File Builder
                   Produces: {slug}_context.json + {slug}_related_mcat_context.json
```

---

## Required Inputs

| # | Input File | Format | Key Columns | Used By |
|---|---|---|---|---|
| 1 | `mcat_list.csv` | CSV | `mcat_id, mcat_name, mcat_url` | All agents (orchestrator iterates per row); Agent 4 safety-net union |
| 2 | `google_search_keywords.csv` | CSV | `mcat_id, MCAT, Query, Clicks, Impressions, Avg_Position` | Agents 3, 12 |
| 3 | `internal_search_keywords.csv` | CSV | `mcat_id, MCAT_Name, keyword, CTR, Pageviews, PDP_Clicks, Calls` | Agents 3, 12 |
| 4 | `mcat_related_categories.csv` | CSV | `glcat_mcat_id, glcat_mcat_name, related_mcat_name` | Agent 4 (existing platform links — to audit, not ground truth) |
| 5 | `related_mcats_overlap.csv` | CSV | `MCAT_1, MCAT_2, MCAT_1_Products, MCAT_2_Products, Common_Product, overlap_pct fields, MCAT_1_Supplier, MCAT_2_Supplier, Common_Suppliers, supplier_overlap_pct fields` | Agent 4 (ALL pairs including non-root, for full family context) |
| 6 | `all_mcats_indiamart.csv` | CSV | `glcat_mcat_id, glcat_mcat_name` | Preprocessor only (~98K rows; never passed to any agent directly) |
| 7 | `preprocessed_candidates.csv` | CSV | `root_mcat_id, root_mcat_name, candidate_mcat_id, candidate_mcat_name, similarity_score, pre_relevance, pre_relationship, pre_note` | Agent 4 (Preprocessor output for THIS MCAT — generated in Pre-Wave) |

**Note on Input 6 → 7:** `all_mcats_indiamart.csv` is never passed to any agent. The Preprocessor (`catalogue_preprocessor.py`) runs per-MCAT in the Pre-Wave, consumes Input 6, and produces Input 7 (`preprocessed_candidates.csv`) for the current MCAT only. Zero token cost — pure Python, no LLM calls. Input 7 is the only catalogue-derived file any agent ever receives.

**Note on Input 4:** `mcat_related_categories.csv` contains IndiaMART's existing platform-level related MCAT links. These represent the current state, not a validated ground truth. Agent 4 must independently audit and reclassify every entry. The file also contains related-MCAT rows for MCATs beyond the root — this gives Agent 4 extended family ecosystem context.

---

## Preprocessor — `catalogue_preprocessor.py`

**Runs:** Per-MCAT, Pre-Wave. Must complete before Wave 0 starts for this MCAT.
**Purpose:** Filters the full ~98K MCAT catalogue down to a small, scored candidate list of MCATs potentially related to the root MCAT. Eliminates the need to pass the full catalogue to any agent. Zero token cost — pure Python, no LLM calls.

**Inputs:**
- `all_mcats_indiamart.csv` — full catalogue (`glcat_mcat_id, glcat_mcat_name`)
- `root_mcat_name` — current MCAT being processed (e.g. `"FRP Swimming Pools"`)
- `root_mcat_id` — current MCAT's ID

**Processing Logic (in order):**

**Step 1 — Keyword tokenisation**
Tokenise `root_mcat_name` into component terms. Strip stop words. Example: `"FRP Swimming Pools"` → `["FRP", "Swimming", "Pools"]`.

**Step 2 — Keyword match scoring**
For every row in `all_mcats_indiamart.csv`, compute a keyword overlap score against root tokens:
- Exact full-name match → score 1.0
- All root tokens present in candidate name → score 0.9
- Majority of root tokens present → score 0.7
- Single meaningful root token present → score 0.4
- No token overlap → score 0.0. Discard immediately.

**Step 3 — Fuzzy string similarity**
For candidates with score > 0.0, compute fuzzy string similarity (e.g. `rapidfuzz` `token_sort_ratio`) between root name and candidate name. Add to score (weighted 0.3×).

**Step 4 — Semantic synonym expansion**
Maintain a lightweight hardcoded synonym map for common IndiaMART taxonomy terms:
- `FRP` ↔ `Fiberglass`, `Fibreglass`, `GRP`
- `Pool` ↔ `Swimming Pool`, `Pools`
- `Prefab` ↔ `Readymade`, `Modular`, `Portable`
- (extend map as catalogue grows)
Re-score any candidates that match via synonym. Boost score by 0.2.

**Step 5 — Threshold and rank**
Keep only candidates with final score ≥ 0.3. Sort descending by score. Cap output at top 100 candidates.

**Step 6 — Pre-label**
Assign lightweight heuristic labels (not LLM, not semantic reasoning):

| `pre_relevance` | Condition |
|---|---|
| `high` | score ≥ 0.7 OR synonym match |
| `medium` | score 0.4–0.69 |
| `low` | score 0.3–0.39 |

| `pre_relationship` | Condition |
|---|---|
| `likely_sibling` | Shares primary noun with root (e.g. both contain "Pool") |
| `likely_parent` | Root name is a substring of candidate name |
| `likely_child` | Candidate name is a substring of root name |
| `unknown` | Score-based match only, no structural inference |

`pre_note`: one short string explaining the match signal (e.g. `"Token match: Swimming, Pools"`, `"Synonym match: FRP→Fiberglass"`).

**Output:** `preprocessed_candidates.csv`

| Column | Description |
|---|---|
| `root_mcat_id` | Root MCAT ID |
| `root_mcat_name` | Root MCAT name |
| `candidate_mcat_id` | Candidate MCAT ID from `all_mcats_indiamart.csv` |
| `candidate_mcat_name` | Candidate MCAT name |
| `similarity_score` | Final composite score (0.0–1.0) |
| `pre_relevance` | `high` / `medium` / `low` |
| `pre_relationship` | `likely_sibling` / `likely_parent` / `likely_child` / `unknown` |
| `pre_note` | Short match-signal explanation |

**Important:** The Preprocessor is a discovery tool. It widens the net. Agent 4 is the decision-maker — it receives this list as one of four candidate sources and independently classifies every entry using full semantic reasoning and overlap data.

---

## Optional Inputs

| Input | Used By | Fallback |
|---|---|---|
| `seller_pdfs` (up to 5 PDFs per MCAT) | Agent 1 | Agent 1 returns null for this MCAT. Agent 3 receives no PDF supplement for this MCAT. |
| `good_products.csv` | Image Pre-loader → Agent 2, 7, 10 | Fallback: `input_data_absent: true`. Columns: `fk_glcat_mcat_id, fk_pc_item_id, pc_item_img_original, product_page_url`. AI-deemed good products — Agent 2 verifies each. Must be paired with `good_images.zip`. |
| `bad_products.csv` | Image Pre-loader → Agent 2, 7, 10 | Same fallback. Same columns. AI-deemed bad products — bad label may indicate wrong image, wrong title, wrong specs, wrong MCAT, or is_service. Agent 2 identifies exactly which attribute(s) failed. Must be paired with `bad_images.zip`. |
| `good_images.zip` | Image Pre-loader → Agent 2 | If absent: Agent 2 does text-only verification (product page only). All image verification fields set to `image_status: missing_from_zip`. Naming convention: `{fk_pc_item_id}.jpeg` (or .jpg / .png). |
| `bad_images.zip` | Image Pre-loader → Agent 2 | Same fallback as `good_images.zip`. Same naming convention. |
| `pns_call_insights_clean.csv` | Agent 3 | Agent 3 builds context from page browse + keywords only. When provided: buyer vocabulary and context supplement. Columns: `mcat_name, product_name, call_id, amount, quantity_value, quantity_unit, spec_name, spec_value, spec_unit`. |

---

## Absent Input Data Fallback Protocol

| Agent | Normal mode | Fallback |
|---|---|---|
| Agent 2 | Fetches + verifies all items from both files; produces verified good/bad lists | Returns `{"input_data_absent": true, ...nulls}` immediately. |
| Agent 7 — relevant photos | Source 1: Agent 2 `verified_good_image_urls`; Source 2: Agent 3 `raw_images` | Source 1 eliminated. Agent 3 `raw_images` + web search only. `source: page_browse_only`. |
| Agent 7 — irrelevant photos | Source 1: Agent 2 `verified_bad_image_urls`; Sources 2–3: page browse + cross-MCAT | Source 1 eliminated. Page browse only. Likely < 10 entries. `photo_count_note` fires. |
| Agent 10 — good examples | Source 1: Agent 2 `verified_good_products`; Source 2: page browse candidates | Source 1 eliminated. All 5 correct from page browse. |
| Agent 10 — incorrect examples | Source 1: Agent 2 `verified_bad_products` (with failure reasons); Source 2: page browse | Source 1 eliminated. All 5 incorrect from page browse. |

Consolidator writes to `context.json` when any agent sets `input_data_absent: true`:
```json
"data_quality_flags": {
  "input_data_absent": true,
  "affected_fields": ["relevant_photos", "irrelevant_photos", "few_shot_examples.good_listings", "few_shot_examples.bad_listings", "wrong_mcat_classifier"]
}
```
When both input files are provided and fully used, `data_quality_flags` is omitted entirely.

---

## Market Research Policy

**PROHIBITED — never use:**
- TradeIndia, Aajjo.com, ExportersIndia, and all Indian B2B marketplace clones
- **IndiaMART listings/pages for price benchmarking** (may be used for product type research and keyword data, never as a price source)

**APPROVED — use for market intelligence:**
- Amazon India / Flipkart (consumer naming conventions, fixed catalogue prices)
- Google Search trends and autocomplete (buyer intent signals)
- Manufacturer and brand websites (first-party product naming and pricing)
- Google Shopping results
- Moglix, Industrybuying (B2B retail platforms with transparent pricing)
- Industry publications, trade associations, BIS/IS standards

---

## Key Design Principles

| Principle | Detail |
|---|---|
| **Two output files, per MCAT** | `{slug}_context.json` + `{slug}_related_mcat_context.json`. No intermediate JSON deliverables. |
| **context.json is AI-readable** | Concise, structured for programmatic consumption. Verbose prose is harmful. `reason`: 2-bullet max. `notes`: 3-sentence max. `summary`: 5-bullet max. |
| **Senior CM knowledge encoding** | Every field encodes what a senior Category Manager would know: contradiction pairs, invalid options, routing targets, wrong product signals. |
| **Real-evidence examples only** | Every listing and image in `few_shot_examples` comes from Agent 2 verified products (top priority) or the actual MCAT page (Agent 10 fallback). No invented or hypothetical examples. Middle-ground excluded — only polar extremes. |
| **Extreme good / extreme bad** | Good: passes all signals with ≥3 specific buyer-attracting attributes. Bad: fails ≥2 signals or commits one catastrophic violation. No middle ground. |
| **Wrong vs thin — strict separation** | `irrelevant_titles`/`irrelevant_photos` = actively wrong or contaminating tokens present. `thin_titles`/`thin_photos` = correct but incomplete. Never penalise for absence. |
| **Anti-hallucination** | No agent may invent specs, options, examples, or URLs without evidence from real page data, keyword data, market research, or provided inputs. Photo URLs and proddetail URLs must be fetched in the current session — never fabricated. |
| **Listing Quality Check** | Agent 3 performs a mandatory buyer-perspective check. `needs_cleaning: yes` cascades to Agent 5 (thumbnail segment rule), Agent 4 (contaminating MCAT classification), and the Consolidator (segment filter). |
| **Segment contamination isolation** | When a sibling MCAT carves out a specific sub-segment of the root, the root MCAT's names, alt names, search queries, product_types, and buyer_segments must not claim that sub-segment. Nine dimensions require active blocking (Agent 12). Consolidator filters all affected fields. |
| **Routing completeness** | Every `wrong_mcat_classifier` class must name a specific target MCAT. Vague routing is not acceptable. |
| **Gating flags as AI config** | `gating_flags` is the control panel for the listing audit AI. Every flag must have an evidence-backed reason. |
| **Structural verdict first** | `structural_verdict` tells the taxonomy team whether to act on the MCAT before cleaning listings. Always includes `proceed_to_cleaning` and `cleaning_blocks_on_structural`. |
| **Buyer-first, data-validated taxonomy** | Classification decisions are made from the buyer's perspective first — then validated using quantitative overlap metrics. |
| **Page-browse for large siblings** | For any sibling with ≥200 products OR ≥100 suppliers, Agent 4 must `web_fetch` that MCAT's page before finalising `is_duplicate`. |
| **Merge inclusiveness** | All 6 signals (S1–S6) are independently evaluated. Thin bifurcations, alias collisions, funnel collapse, and nature weakness are all merge signals. |
| **Category nature per related MCAT** | Every related MCAT gets the full 6-dimension classification (Agent 4). Reported in `related_mcat_context.json`. |
| **Alias collision as merge signal** | When Agent 12 naturally generates a name matching a related MCAT, record it as merge signal S3. |
| **Brand MCAT protection** | Brand MCATs: always `is_duplicate: no, to_be_merged: no`. Never in `structural_verdict.mcats_to_absorb`. |
| **Parent direct-match override** | If a parent MCAT's name = semantic equivalent of root: `is_duplicate: yes, to_be_merged: yes`. Root merges INTO the parent. |
| **Market-validated outputs** | Every agent cross-references external market data (approved sources only). |
| **unit_important High only when genuinely variable** | High = unit is variable, mismatch breaks price comparability. Low = universally fixed, no alternative. Finished catalogue products always Low. |
| **AI attribution watermark** | All AI-generated thumbnails: white "IndiaMART AI" text, dark semi-transparent pill, 10–12px, 60–70% opacity, bottom-right corner. |
| **Clear scope separation** | Listing image type = OCR extractability. MCAT thumbnail = AI-generated category image. Separate agents. |
| **Name–taxonomy collision prevention** | Enhanced names and alt names must not match any live related MCAT name unless `is_duplicate: yes` AND `to_be_merged: yes`. |
| **No data duplication** | Each fact in exactly one field. Canonical sources: `gating_flags.canonical_unit` for unit; `mcat_description.product_types` for variants; `wrong_mcat_classifier` for routing targets. |
| **Narrow agent scope** | Each agent does one thing. Separation of concerns keeps agents fast, testable, and replaceable. |

---

## Conciseness Rules for context.json (mandatory for Consolidator)

| Field | Limit |
|---|---|
| `mcat_description.long` | Max 4 sentences. No lists. No price figures. |
| `gating_flags.reason` | Max 3 sentences. One sentence per flag cluster. |
| `category_nature.reason` | Max 2 bullets. |
| `structural_verdict.summary` | Max 5 bullets. |
| `irrelevant_titles.failure_classes[].signal` | One sentence — wrong token present, never absent. |
| `thin_titles.thinness_signals[]` | One sentence — what useful token is absent. |
| `wrong_mcat_classifier.classes[].signal` | One sentence. |
| `mcat_thumbnail_images[].rationale` | Max 2 sentences. |
| All other `reason` fields | 2 bullets maximum. |

---

## Agent Reference

---

### Agent 1 — PDF Enricher
**Runs:** Per-MCAT, Wave 0 (before Agent 3). Processes up to 5 seller PDFs specific to this MCAT.
**Role:** Extracts structured product and specification data from seller PDFs (catalogues, spec sheets, brochures) for the current MCAT. Each PDF is processed independently, all results are merged into one JSON, then filtered to only the products/data identified for the current MCAT. The filtered output supplements Agent 3. If no PDFs are provided for this MCAT, return null immediately.

**Inputs:** `seller_pdfs` (up to 5 PDFs for THIS MCAT — optional), `mcat_name` (used as Target Category)

**If null or empty:** Return `{"pdf_summary": null}` immediately. Agent 3 receives no PDF supplement for this MCAT.

---

**Processing Steps (execute in order):**

**Step 1 — Per-PDF Extraction**
For each of the up to 5 PDFs, apply the following extraction prompt independently. Analyse both the document images and OCR text:

```
Role: You are a precise Data Extraction Agent specializing in product catalogs
and technical brochures.

Task: Analyze the provided document (images and OCR text) to extract all products
and services into a structured JSON format.

Target Category: "{{mcat_name}}"

Categorization Logic:
  1. Identified for input category: Only include products that explicitly match
     the Target Category above.
  2. Other categories: Include all other products, equipment, accessories, or
     services mentioned in the document that do not match the Target Category.
  3. Unidentified: Include any images or text segments that appear to be products
     but lack sufficient names or descriptions to categorize.

Extraction Rules:
  - No Fabrication: If a field like "Product Price," "Product Specifications,"
    or "Product Units" is not explicitly stated in the text, populate it as
    "Not available".
  - Data Synthesis: Write the "Product Description" by combining OCR text with
    visual details from the images.
  - Image Description: Provide a literal description of the product as it appears
    in the screenshot (e.g., color, shape, setting).
  - Completeness: Ensure every item pictured or listed is captured in one of the
    three sections.

Required JSON Structure:
{
  "Identified for input category ({{mcat_name}})": [
    {
      "Product Category": "",
      "Product Name": "",
      "Product Description": "",
      "Product Specifications": "",
      "Product Price": "",
      "Product Units": "",
      "Product Image descriptions": ""
    }
  ],
  "Other categories": [
    {
      "Product Category": "",
      "Product Name": "",
      "Product Description": "",
      "Product Specifications": "",
      "Product Price": "",
      "Product Units": "",
      "Product Image descriptions": ""
    }
  ],
  "Unidentified": [
    {
      "Context": "Description of why the item is unidentified",
      "Image Description": ""
    }
  ]
}
```

This produces one JSON object per PDF: `pdf_1_raw`, `pdf_2_raw`, … `pdf_5_raw`.

---

**Step 2 — Merge All PDFs into One Combined JSON**
Merge all per-PDF JSONs (`pdf_1_raw` … `pdf_N_raw`) into a single combined JSON by concatenating each section:
- `"Identified for input category"`: union of all matching items across all PDFs. Deduplicate by `Product Name` + `Product Specifications` (keep the richer entry).
- `"Other categories"`: union of all non-matching items across all PDFs. Deduplicate similarly.
- `"Unidentified"`: union of all unidentified items across all PDFs.
- Record `pdf_count_processed` = number of PDFs actually processed (≤5).

---

**Step 3 — Filter to Identified Category Only (output for Agent 3)**
From the merged JSON, extract **only** the `"Identified for input category"` list.
This is the `agent1_pdf_supplement` passed to Agent 3.
Agent 3 must not receive `"Other categories"` or `"Unidentified"` items — those sections remain in the full merged JSON for audit/logging purposes only.

---

**Output schema:**
```json
{
  "pdf_summary": {
    "pdf_count_processed": 0,
    "mcat_name": "{{mcat_name}}",
    "agent1_pdf_supplement": [
      {
        "Product Category": "",
        "Product Name": "",
        "Product Description": "",
        "Product Specifications": "",
        "Product Price": "",
        "Product Units": "",
        "Product Image descriptions": ""
      }
    ],
    "full_merged_json": {
      "Identified for input category": [],
      "Other categories": [],
      "Unidentified": []
    }
  }
}
```

**`agent1_pdf_supplement`** — passed to Agent 3. Contains only identified-category products.
**`full_merged_json`** — retained for audit/logging. Never passed to downstream agents.

---

### Agent 2 — Product & Image Verifier
**Runs:** Per-MCAT, Wave 0. Processes both input product files for this MCAT.
**Role:** Verifies AI-deemed good and bad product classifications by inspecting each item's image and product page. Resolves conflicts. Produces verified good and bad lists that supplement Agents 7 and 10 as the highest-priority source for photo examples and listing examples. Not ground truth input — independent verification is mandatory.

**Inputs:**
- `enriched_products` list from the Image Pre-loader. Each item has:
  - `item_id` — `fk_pc_item_id` from the CSV
  - `ai_label` — `"good"` or `"bad"` (from which file it came)
  - `image_url` — original `pc_item_img_original` URL (for reference only)
  - `image_base64` — base64-encoded image from the zip file (may be null)
  - `image_mime_type` — e.g. `image/jpeg`
  - `image_status` — `"ok"` | `"missing_from_zip"`
  - `product_page_url` — IndiaMART proddetail URL

**If enriched_products list is empty or null:**
Return `{"input_data_absent": true, "verified_good_products": [], "verified_bad_products": [], "conflicts_resolved": [], "image_pattern_summary": null, "verified_good_image_urls": [], "verified_bad_image_urls": []}` immediately.

**If provided — execute steps in order:**

**Step 1 — Collect and flag conflicts**
Collect all items from the enriched_products list. Identify any `item_id` that appears with BOTH `ai_label: good` AND `ai_label: bad` — these are conflicts requiring resolution in Step 5.

**Step 2 — Inspect every item**
For EVERY item (good + bad + conflict), perform both inspections:
- **Visual (image):** If `image_status: ok` — analyse the pre-loaded `image_base64` directly. Describe what is literally visible: product type, material, context, angle, background, any text/watermarks visible. If `image_status: missing_from_zip` — note in `verification_note`, proceed with text-only verification for this item.
- **Text (product page):** `web_fetch` the `product_page_url` — extract: listing title, price, spec table, MCAT breadcrumb.

**Step 3 — Verify good-list items**
For each item in `good_products.csv`:
- Ask: Does the image show a correct, clearly identifiable product for this MCAT? Does the page confirm correct category, coherent specs, and a buyer-ready title?
- If YES → `verified_label: good`, `override: false`
- If NO → `verified_label: bad`, `override: true`. Record `failure_reason` and `correct_mcat_suggestion`.
- If page is dead / image broken → `verified_label: inconclusive`, `override: false`.

**Step 4 — Verify bad-list items**
For each item in `bad_products.csv`:
- Ask: What specifically is wrong? Identify which attribute(s) fail from this enum: `wrong_product | wrong_mcat | wrong_material | is_service | inflatable | accessory | construction_service | thin_image | other`
- If the failure is confirmed → `verified_label: bad`, `override: false`. Record `failure_reason`.
- If on inspection the item is actually correct → `verified_label: good`, `override: true`.
- Record `correct_mcat_suggestion` where the item belongs if it is wrong MCAT.

**Step 5 — Resolve conflicts**
For items in both files: the Step 2–4 inspection determines the resolved label. Record in `conflicts_resolved[]` with `resolution_note` explaining which attribute failed or passed.

**Step 6 — Build verified lists**
- `verified_good_products`: items with `verified_label: good` (from either file, including overrides)
- `verified_bad_products`: items with `verified_label: bad` (from either file, including overrides)
- `verified_good_image_urls`: image URLs from `verified_good_products`
- `verified_bad_image_urls`: image URLs from `verified_bad_products`

**Step 7 — Summarise good image patterns**
From `verified_good_image_urls`: identify visual patterns common to verified good images (background, product angle, colour, clarity, context). 2–3 sentences.

**Output schema:**
```json
{
  "input_data_absent": false,
  "verified_good_products": [
    {
      "item_id": "",
      "image_url": "",
      "image_status": "ok | missing_from_zip",
      "product_page_url": "",
      "ai_label": "good",
      "verified_label": "good | bad | inconclusive",
      "override": false,
      "verification_note": "1 sentence — what was confirmed or what failed (image + page)"
    }
  ],
  "verified_bad_products": [
    {
      "item_id": "",
      "image_url": "",
      "image_status": "ok | missing_from_zip",
      "product_page_url": "",
      "ai_label": "bad",
      "verified_label": "good | bad | inconclusive",
      "override": false,
      "failure_reason": "wrong_product | wrong_mcat | wrong_material | is_service | inflatable | accessory | construction_service | thin_image | other",
      "correct_mcat_suggestion": "Specific MCAT name or null",
      "verification_note": "1 sentence — specific attribute that failed"
    }
  ],
  "conflicts_resolved": [
    {
      "item_id": "",
      "ai_labels": ["good", "bad"],
      "resolved_label": "good | bad | inconclusive",
      "resolution_note": "1 sentence"
    }
  ],
  "image_pattern_summary": "2–3 sentence description of what verified good images have in common",
  "verified_good_image_urls": ["https://5.imimg.com/..."],
  "verified_bad_image_urls": ["https://5.imimg.com/..."]
}
```

---

### Agent 3 — Context Extraction + Market Research + Listing Quality Check
**Runs:** Per-MCAT, Wave 1. Foundation agent — all Wave 2 agents depend on this output.
**Role:** Browses the MCAT page, conducts external market research, parses keyword files, performs listing quality check, and synthesises supplementary inputs (PDF summary from Agent 1, buyer call data).

**Inputs:** `mcat_name`, `mcat_id`, `product_page_url`, internal KWs, google KWs, `agent1_pdf_supplement` (may be null — identified-category products only, pre-filtered by Agent 1), `seller_buyer_call_data` rows for this MCAT (may be empty)

**Execute steps in order:**

**Step 1 — Browse the IndiaMART MCAT page**
`web_fetch` the `product_page_url`. Extract: page title, meta description, meta keywords, H1, product types, subcategories, price ranges, related category links, alt names, seller geography, top 8–10 listing tiles (title, price, spec snippet, image URL, proddetail URL).

**Step 2 — Listing Quality Check (mandatory)**
Ask: *"If a buyer searched for [MCAT Name] and landed on this page, would ALL visible listings make sense to them?"*

- Industrial + domestic variants mixed → `needs_cleaning: yes`
- Ambiguous name attracting two completely different buyer types → `needs_cleaning: yes`
- Price range >2 orders of magnitude due to segment mixing (not size variation) → `needs_cleaning: yes`
- All listings same product family, same buyer intent → `needs_cleaning: no`

```
Example 1 — needs_cleaning: yes
  MCAT: "Oil Burners"
  Page: Aroma diffusers (₹200–₹2,000) + industrial diesel burners (₹50,000–₹5,00,000)
  → reason: "Two completely different buyer intents co-mingled. Home décor buyer confused
    by industrial combustion equipment."

Example 2 — needs_cleaning: no
  MCAT: "FRP Swimming Pools"
  Page: Rectangular FRP pools, oval FRP pools, rooftop FRP pools — all FRP, all for swimming
  → reason: "All listings are FRP swimming pools. Variation is only size and application."

Example 3 — needs_cleaning: yes
  MCAT: "Pressure Pumps"
  Page: Domestic water booster pumps + high-pressure industrial hydraulic pumps
  → reason: "Incompatible buyer intents and price segments."
```

**Step 3 — External market research**
`web_fetch` 2–3 pages from approved sources (Amazon India, Google Shopping, manufacturer sites, Moglix, Industrybuying). Extract: market naming conventions, product types, price ranges per tier, buyer-facing attributes.

**Step 4 — Parse keyword files**
Internal KWs: top 15 by Pageviews, note CTR and PDP Click patterns.
Google KWs: top 15 by Impressions, note Click patterns and avg position.

**Step 5 — Supplement from Agent 1 PDF data**
If `agent1_pdf_supplement` is not null and not empty:
- All items in this list have already been filtered to the current MCAT's category by Agent 1. Use them directly — do not re-filter.
- Cross-reference `Product Name` and `Product Description` to enrich `product_types` and `alt_names`.
- Cross-reference `Product Specifications` to add valid spec options and technical terminology.
- Use `Product Price` values (where not "Not available") as supplementary price anchors — note the source as PDF.
- Add any new technical terms or brand names from `Product Name`/`Product Description` fields to `alt_names` where relevant.
- Use `Product Image descriptions` to validate or enrich `thumbnail_image_description`.
- PDF data SUPPLEMENTS — it does not override page observations. If PDF data contradicts live page data, prefer the page.

**Step 6 — Supplement from seller_buyer_call_data**
If call rows exist: extract buyer vocabulary, applications mentioned, buyer segments represented, confusion patterns, price ranges discussed. Call data SUPPLEMENTS — it adds buyer-side context. Do NOT extract specs from call data. Do NOT let call data override page observations.

**Step 7 — Scrape raw listings and images**
Record full listing data for Agent 10: titles, prices, spec snippets, image URLs, proddetail URLs.

**Output fields:**
| Field | Description |
|---|---|
| `mcat_description.short` | 1–2 sentence definition: what it is, how sold, what made of |
| `mcat_description.long` | 4-sentence max expert description |
| `mcat_description.product_types` | All distinct product types/variants — canonical source |
| `mcat_description.primary_applications` | Real-world use cases, enriched by call data |
| `mcat_description.buyer_segments` | Who buys and in what context, enriched by call data |
| `listing_quality.needs_cleaning` | `yes` / `no` |
| `listing_quality.reason` | 2-bullet explanation |
| `listing_quality.primary_segment` | When needs_cleaning: yes — name the primary segment |
| `price_range` | Observed price band |
| `alt_names` | Alternate names from page + market + call data buyer vocabulary |
| `top_internal_keywords` | Top 15: `{keyword, pageviews, pdp_clicks, calls}` |
| `top_google_keywords` | Top 15: `{query, clicks, impressions, avg_position}` |
| `market_context` | External market naming norms, price tiers |
| `page_metadata` | `{title, meta_desc, meta_keywords, h1}` |
| `thumbnail_image_description` | Description of current MCAT thumbnail |
| `raw_listings` | list[dict]: `{title, price, specs_snippet, image_url, proddetail_url}` → Agent 10 |
| `raw_images` | list[dict]: `{url, listing_context}` → Agent 7 |
| `call_data_buyer_vocabulary` | Distinct buyer terms from call data not in alt_names |
| `call_data_context_note` | 1–2 sentences on what call data revealed that the page did not |

---

### Agent 4 — MCAT Relationship Mapper
**Runs:** Per-MCAT, Wave 2 (parallel).
**Role:** Builds and classifies the full related MCAT candidate pool for the root MCAT. Receives candidates from four sources, unions them, deduplicates, and independently audits and classifies every entry. Produces the full related MCAT taxonomy. Does NOT trust any source as ground truth.

**Inputs:**
- `vision_output` (Agent 3)
- `mcat_related_categories.csv` — existing platform links (to audit, not trust)
- `related_mcats_overlap.csv` — ALL pairwise overlap data in the family including non-root pairs (for family context)
- `preprocessed_candidates.csv` — scored candidates for THIS MCAT from the Preprocessor
- `mcat_list.csv` — full MCAT batch list (safety net)

---

**Step 1 — Build the candidate pool (union of all four sources)**

Pull candidates from each source independently, then union and deduplicate by `mcat_name` (case-insensitive):

**Source A — `mcat_related_categories.csv`:**
Filter rows where `glcat_mcat_name` = root MCAT name. Extract all `related_mcat_name` values.
These are the existing platform-assigned related MCATs. Treat as candidates to audit — not as correct answers.

**Source B — `related_mcats_overlap.csv` (root pairs):**
Extract all rows where `MCAT_1` = root MCAT name OR `MCAT_2` = root MCAT name. The counterpart MCAT in each row is a candidate. Attach overlap metrics: `common_products`, `product_overlap_pct (M1.M2)/M1`, `product_overlap_pct (M1.M2)/M2`, `common_suppliers`, `supplier_overlap_pct` fields.

**Source C — `related_mcats_overlap.csv` (non-root family pairs — for family context):**
From Source A's candidate list, also pull all overlap rows where BOTH `MCAT_1` and `MCAT_2` are family members (neither is the root). Do not add new candidates from this step. Use this data only to understand how family members relate to each other — which pairs are near-duplicates, which are thin, which have high cross-overlap — as context for classifying each candidate's relationship to the root.

Example for FRP Swimming Pools: `Round Swimming Pools ↔ Readymade Swimming Pools`, `Prefab ↔ Portable`, `Inflatable ↔ Kids Swimming Pool` — none of these involve the root but they reveal the family's internal structure.

**Source D — `preprocessed_candidates.csv`:**
Filter rows where `root_mcat_id` = this MCAT's ID. Add any candidate not already in the pool. Use `pre_relevance` and `pre_relationship` as lightweight signals only — Agent 4's own classification always takes precedence.

**Source E — `mcat_list.csv` (safety net):**
Check every MCAT in `mcat_list.csv`. Any MCAT not already in the candidate pool (from Sources A–D) must be added. All MCATs in the batch belong to the same family by definition — none may be silently omitted.

After union: deduplicate. Record `source_flags` per candidate (which sources it appeared in — A, B, C, D, E).

---

**Step 2 — Attach overlap data to every candidate**

For each candidate in the pool, look up its row(s) in `related_mcats_overlap.csv` where it appears against the root. Populate:
- `total_products` and `total_suppliers` for the candidate
- `overlap_with_root`: `common_products`, `common_suppliers`, `product_overlap_pct`, `supplier_overlap_pct`
- If no overlap row exists for a candidate, set all overlap fields to 0.

Also build a **family context note** for each candidate using non-root pairs (Source C): summarise in 1 sentence how this candidate relates to other family members (e.g. "High overlap with Readymade Swimming Pools (11.36%) and Portable Swimming Pools — suggests near-duplicate cluster in lower-end segment").

---

**Step 3 — Classify each candidate**

For each candidate, independently determine:

**3a — Relationship (12-value enum):**
`super_parent | parent_category | sibling_category | brand_mcat | cross_sell | upsell | downsell | accessory | parts | service | substitute | unrelated`

Classification must be buyer-perspective first, then validated by overlap data.
- High product overlap (>15% from root's side) + same buyer intent → likely `sibling_category` or `parent_category`
- Same buyer, narrower scope → `sibling_category`
- Same buyer, broader scope → `parent_category` or `super_parent`
- Different buyer, complementary → `cross_sell` / `accessory` / `parts`
- Different buyer, incompatible → `unrelated`

**3b — Sibling bifurcation type (when `relationship: sibling_category`):**
`material | brand | technology | application | condition | form_factor | capacity_size | fuel_energy | segment | specification | output_type | geographic | composite`

**3c — Duplicate / merge flags:**
`is_duplicate`, `to_be_merged`, `is_overlapping` — apply merge signals S1–S6.

**3d — Category Nature (6 dimensions per candidate):**

| Dimension | `yes` | `no` |
|---|---|---|
| `is_generic` | High-volume, broad, roll-up node | Specific, bounded, niche |
| `is_specific` | Well-scoped, clear buyer intent | Broad, vague, diffuse |
| `is_vague` | Ambiguous name, mixed intents | Clear and unambiguous |
| `is_thin` | Insufficient volume to stand alone | Sufficient volume and demand |
| `is_branded` | Anchored to specific brand/trademark | Generic/material/function-based |
| `is_service` | Service offering | Physical product |

---

**Mandatory Page-Browse Rule:**
For any candidate with **≥200 products OR ≥100 suppliers**: `web_fetch` that MCAT's IndiaMART page before finalising `is_duplicate`. Answer:
1. Visual equivalence — same physical product as root?
2. Spec equivalence — spec snippets overlap substantially?
3. IndiaMART cross-reference — root shown as related link on this page?

**Override Rule A — Brand MCAT Protection:**
Brand MCAT = name anchored to single commercial brand/manufacturer. Always: `is_brand_mcat: yes`, `is_duplicate: no`, `to_be_merged: no`, `is_overlapping: yes`, `relationship: sibling_category`. `routing_note` always starts: `"BRAND MCAT — do NOT absorb, do NOT mark as duplicate."` Never in `structural_verdict.mcats_to_absorb`.

**Override Rule B — Parent Direct-Match Check:**
Test: "Is the parent MCAT name just a longer/more formal way of saying the same thing as the root?"
- YES → `is_duplicate: yes, to_be_merged: yes` (root merges INTO parent as canonical)
- NO → `is_duplicate: no, to_be_merged: no`

**Segment Isolation Rule:**
When Agent 3 flags `needs_cleaning: yes`: identify candidates belonging to the contaminating segment and classify them as `relationship: unrelated`.

**Output:** Full `related_mcats` list + slim output (name, mcat_id, relationship, sibling_bifurcation_type, is_duplicate, to_be_merged, is_brand_mcat, merge_signals_fired, category_nature.is_thin, category_nature.is_vague, source_flags)

---

### Agent 5 — Name + Image Audit
**Runs:** Per-MCAT, Wave 2 (parallel).
**Role:** Evaluates the current MCAT name and thumbnail image for accuracy. Produces 3 AI thumbnail image descriptions. `thumbnail_audit` is nested inside `structural_verdict` in `context.json`.

**Inputs:** `vision_output` (Agent 3 — includes `listing_quality`), `thumbnail_image_url`

**Name Audit:** Cross-reference MCAT name against top internal KWs, Google KWs, Amazon India, Google Shopping, manufacturer sites.

**Thumbnail Audit:** `current_thumbnail_correct: false` ONLY if: shows wrong product, shows brochure/catalogue instead of product, no product visible, seller watermark obstruction.

**⛔ CRITICAL — Thumbnail suggestions must match primary segment:**
When `listing_quality.needs_cleaning: yes`, all 3 thumbnail suggestions MUST represent `listing_quality.primary_segment` ONLY.

```
WRONG (mixed MCAT "Oil Burner", primary: industrial combustion):
  ✗ "Decorative soapstone aroma oil burner with tea light candle"
  ✗ "Industrial monoblock oil burner"
  ✗ "Waste oil cooking stove"
  → BAD: spans 3 segments

CORRECT:
  ✓ "Compact red/orange monoblock industrial oil burner on white background"
  ✓ "Industrial oil burner mounted on boiler in factory setting"
  ✓ "Close-up of oil burner flame head with atomiser nozzle and electrodes"
  → GOOD: all 3 = industrial combustion only
```

**Output:** `mcat_name_audit` (verdict, reason), `mcat_image` (quality, correctness, issues), `thumbnail_audit` (current_thumbnail_correct, reason), `mcat_image_suggestions` (list[3])

---

### Agent 6 — Buyer Display Importance
**Runs:** Per-MCAT, Wave 2 (parallel).
**Role:** Determines which display signals matter most to buyers. Output becomes `gating_flags` in `context.json`.

**Inputs:** `vision_output` (Agent 3)

**Unit Decision Process — 3 Steps (must do all 3):**

**Step 1 — Research how sellers actually quote.**
Search Google for "[MCAT name] price" and "[MCAT name] quotation format". Check Amazon India, manufacturer sites, industry forums for real-world transaction unit.

**Step 2 — Model the actual buyer-seller interaction.**
- Custom-made to buyer's dimensions → unit follows the variable dimension (per sq ft, per metre)
- Fixed catalogue product → `per piece`
- Weight/volume of material → weight/volume unit
- Example: Swimming pool buyer discusses L×W → seller quotes per sq ft. Despite per-piece listings on IndiaMART, actual deal is dimension-driven.

**Step 3 — Check for sub-segments with different units.**
Map major sub-types to natural units. Flag in `unit_note` if sub-segments diverge.

**unit_important High vs Low:**
- **High** = unit is variable in this MCAT. Mismatch breaks price comparability.
- **Low** = unit is universally fixed. No alternative exists. No mismatch possible.
- **Rule: if "no buyer would ever be confused about the unit" → set Low.**

| Buying Pattern | Canonical Unit | Typical Categories |
|---|---|---|
| Custom-made, area-based | `per sq ft` | Custom pools, flooring, wall cladding |
| Custom-made, linear | `per running foot` | Custom pipes, cables, fabric |
| Finished catalogue product | `per piece` | Kids pools, appliances, machines |
| Raw material / commodity | `per kg` / `per litre` | Chemicals, metals, paints |
| Service | `per project` / `per sq ft` | Pool construction, consulting |

```
Example 1 — FRP Swimming Pools: per sq ft (market research overrides listing observation)
  Listing observation: Mix of per sq ft and per piece
  Market research: Industry norm = per sq ft of surface area. Sellers ask for L×W before quoting.
  → unit_important: high, recommended_unit: "per sq ft"
  → unit_note: "Exception: small kids' splash pools are fixed catalogue — per piece."

Example 2 — Office Chairs: per piece, unit_important Low
  All listings, all channels, all buyers: per piece. No alternative exists.
  → WRONG to set High. "Per piece is the only unit" IS the argument for Low.
```

**buyer_attracting_attributes:** What makes a buyer pick THIS listing over 10 others?
- Industrial: technical specs (pressure rating, flow rate, material grade)
- Aesthetic/sensory: fragrance, colour, finish, design pattern
- Services: rate/pricing metrics, scope

**Output per signal** (price, image, unit, specification):
- `level`: `high` / `low`
- `reason`: 2-bullet justification
- For `unit` additionally: `recommended_unit`, `unit_reasoning_source`, `unit_note`
- For `specification` additionally: `show_on_listing` (bool), `buyer_attracting_attributes` (list[str])

---

### Agent 7 — Listing Image Type Classifier + Photo Examples
**Runs:** Per-MCAT, Wave 2 (parallel).
**Role:** Two responsibilities: (1) classify listing image type (OCR extractability), (2) produce 10 relevant and 10 irrelevant photo examples.

**Inputs:** `vision_output` (Agent 3 — includes `raw_images`), Agent 2 `verified_good_image_urls` + `verified_bad_image_urls` + `verified_bad_products` (with `failure_reason` per item)

**⛔ HARD STOP — NO INVENTED URLS.** Every URL must be real: from Agent 2 verified lists, Agent 3 `raw_images`, or a URL fetched in this session.

**Part 1 — Listing Image Type:**

| Type | OCR Definition |
|---|---|
| `object_only` | OCR cannot extract useful text from product images. Product appearance IS the information. (Pools, machines, sarees, furniture.) |
| `object_with_info` | OCR can extract meaningful product information. Product has text printed/labelled on it. (Medicines, FMCG, packaged food, electronics.) |

**Part 2 — Photos:**

Relevant photo source priority:
1. **Agent 2 `verified_good_image_urls`** — highest priority. Already inspected and confirmed correct.
2. **Agent 3 `raw_images`** — supplement if Agent 2 verified list has < 10 good images.
3. **Web search** — only if Sources 1+2 together have < 10 relevant images. Use approved sources only.
Fallback (input_data_absent): Sources 2–3 only. `source: page_browse_only`, `input_data_absent: true`.

Irrelevant photo source priority:
1. **Agent 2 `verified_bad_image_urls`** — highest priority. Include `failure_reason` per image in `failure_class`.
2. **Agent 3 page-browse wrong products** — supplement if Agent 2 verified bad list < 10.
3. **Cross-MCAT images** — last resort.
Fallback (input_data_absent): Sources 2–3 only. `source: page_browse_only`, `input_data_absent: true`.

**Selection for irrelevant:** Wrong product category, wrong material, accessory-only, decorative-in-industrial, service-listing image. NOT merely blurry — blurry goes in `thin_photos`.

**Output:** `image_type_recommendation` (type, reason, ocr_useful), `relevant_photos` (list[10]), `irrelevant_photos` (list[≤10]), `thin_photos` (list[≤5]), `photo_count_note`, `input_data_absent`

`failure_class` enum: `wrong_product | wrong_material | accessory_only | condition_mismatch | decorative_contamination | is_service | inflatable`

Where `failure_class` is sourced from Agent 2 `verified_bad_products.failure_reason`, map directly. For page-browse-sourced irrelevant images, Agent 7 assigns `failure_class` independently.

---

### Agent 8 — Category Nature
**Runs:** Per-MCAT, Wave 2 (parallel).
**Role:** Classifies the root MCAT across 6 independent boolean dimensions. Feeds `gating_flags`, `structural_verdict`, and Agent 14's merge logic.

**Inputs:** `vision_output` (Agent 3)

| Dimension | `yes` | `no` |
|---|---|---|
| `is_generic` | High-volume, broad, catch-all, roll-up node | Specific, bounded, niche |
| `is_specific` | Well-scoped, clear buyer intent | Broad, vague, diffuse |
| `is_vague` | Ambiguous name, mixed intents | Clear and unambiguous |
| `is_thin` | Insufficient volume to stand alone | Sufficient volume and demand |
| `is_branded` | Anchored to brand/trademark | Generic/material/function-based |
| `is_service` | Service offering | Physical product |

```
"FRP Swimming Pools" → is_generic:no, is_specific:yes, is_vague:no, is_thin:no, is_branded:no, is_service:no
"Swimming Pools"     → is_generic:yes, is_specific:no, is_vague:no, is_thin:no, is_branded:no, is_service:no
"Oil Burners"        → is_generic:no, is_specific:no, is_vague:yes, is_thin:no, is_branded:no, is_service:no
"Hexagonal FRP Plunge Pools" → is_generic:no, is_specific:yes, is_vague:no, is_thin:yes, is_branded:no, is_service:no
```

**Output:** `{is_generic, is_specific, is_vague, is_thin, is_branded, is_service, reason: "2-bullet"}`

---

### Agent 9 — Listing Governance
**Runs:** Per-MCAT, Wave 2 (parallel).
**Role:** Determines whether listing titles should be allowed to contain location names or business-type identifiers.

**Inputs:** `vision_output` (Agent 3)

**Location exception (`location_exception: true`):** Grant ONLY when location is a genuine buyer decision factor — GI-tagged products, regional origin products, location-defined services. NOT industrial machinery or nationwide commodities.

**Business-type exception (`biz_exception: true`):** Grant ONLY when business type is a genuine buyer filter — "Authorised Dealer" or "Manufacturer" where distinguishing OEM from reseller materially affects the transaction.

**Output:** `{location_exception: bool, location_exception_reason, biz_exception: bool, biz_exception_reason}`

---

### Agent 10 — Listing Examples Extractor
**Runs:** Per-MCAT, Wave 2 (parallel).
**Role:** Fetches real listings from the MCAT page, selects 5 extreme-good + 5 extreme-bad examples. Mandatory no-fabrication rule.

**Inputs:** `vision_output` (Agent 3), `mcat_page_url`, Agent 2 `verified_good_products` + `verified_bad_products` (optional — use if not null)

**⛔ MANDATORY — NO FABRICATION:**
MUST fetch the MCAT page and individual listing pages before writing any example. May NOT use invented, hypothetical, or training-knowledge examples.

**Mandatory Execution Steps (in order):**
1. `web_fetch` the MCAT page URL — extract all visible listing tiles.
2. *(Skip if Agent 2 `input_data_absent: true`)* Ingest Agent 2 verified lists with priority:
   - **Good slots:** For each item in `verified_good_products` — `web_fetch` the `product_page_url`, confirm listing is still live, extract full title, specs, price, image. Record `source: verified_good`. These fill the correct slots first.
   - **Bad slots:** For each item in `verified_bad_products` — `web_fetch` the `product_page_url`, confirm still live, extract full listing. Use `failure_reason` from Agent 2 as the primary signal for what went wrong. Record `source: verified_bad`. These fill the incorrect slots first.
3. Shortlist remaining candidates from page browse to fill any unfilled slots (correct or incorrect).
4. `web_fetch` each page-browse candidate's `proddetail` URL — extract full spec table, image URLs, price.
5. Score each against criteria.
6. Select final 5 correct + 5 incorrect. Verified items fill slots first; page-browse fills remaining gaps. When Agent 2 `input_data_absent: true`: all 10 from page-browse, `source: page_browse`, `input_data_absent: true`.

**Scoring:**
- Extreme good = passes ALL signals with ≥3 specific buyer-attracting attributes + zero placeholder specs
- Extreme bad = actively wrong content (wrong material, contamination, wrong MCAT product, spec contradictions) — fails ≥2 signals OR commits one catastrophic violation. **A merely thin/incomplete listing is NOT extreme bad.**

**`verdict` enum (4 values):** `correct | incorrect | incorrect_title | incorrect_specs`
- `incorrect_title` — title contains contaminating/wrong tokens
- `incorrect_specs` — spec-level contradiction or invalid option

**`outlier` `_reason` fields must identify a WRONG THING PRESENT — never a missing thing.**

**`wrong_mcat_classifier` assembly:**
From: (a) incorrect examples, (b) Agent 2 `verified_bad_products` `correct_mcat_suggestion` fields if provided, (c) Agent 4 edge routing notes.
Every class names a specific target MCAT. When `input_data_absent: true`: built from (a) and (c) only.

**Output:** `good_listings`, `bad_listings`, `good_images`, `bad_images_wrong`, `bad_images_thin`, `relevant_titles`, `thin_titles`, `irrelevant_titles`, `wrong_mcat_classifier`

---

### Agent 11 — Company Importance Classifier
**Runs:** Per-MCAT, Wave 2 (parallel).
**Role:** Determines how important company/brand identity is for buyers in this MCAT.

**Inputs:** `vision_output` (Agent 3)

**company_important:**
- `High` — Brand name materially affects buyer trust/authenticity. Buyers specifically search by brand. Counterfeits are a known problem.
- `Medium` — Established brands exist but significant unbranded market also exists.
- `Low` — Brand is not a meaningful decision factor. Buyers compare specs and price.

**Additional output fields:**
- `brand_in_title` — `relevant` (helps buyers identify genuine products) / `contamination` (false claim)
- `trademark_risk` — `yes/no` — known counterfeit/brand hijacking problem?
- `authorised_dealer_brand_exception` — `yes/no` — does "Authorised Dealer" warrant `biz_exception: true` specifically here?

**Output:** `{company_important, importance_driver, brand_in_title, brand_in_title_reason, trademark_risk, trademark_risk_note, authorised_dealer_brand_exception, authorised_dealer_reason}`

---

### Agent 12 — Name Generator
**Runs:** Per-MCAT, Wave 3a (alone — must complete before Agent 14).
**Role:** Produces 4 enhanced name variants, up to 10 alt names, `alias_collision_merge_signals`, and segment contamination output. Enforces the name collision rule and the full 9-dimension segment contamination rule.

**Inputs:** `vision_output` (Agent 3 — keyword data), Agent 4 slim output

**Step 1 — Trigger Detection (before generating any candidates):**
Scan Agent 4 slim output for sibling MCATs. Check each sibling name against signal words in the table below.

**Full 9-Dimension Segment Contamination Rule:**

| Dimension | Signal words in sibling MCAT name | Synonym cluster to block in root |
|---|---|---|
| **Condition — used market** | Refurbished, Used, Second Hand, Pre-owned, Reconditioned, Old, Rebuilt | used, second hand, pre-owned, old, refurbished, reconditioned, rebuilt, ex-demo, previously used |
| **Size tier — small** | Mini, Micro, Compact, Small, Nano, Pocket | mini, micro, compact, small, nano, miniature, pocket-size, tiny |
| **Size tier — large/heavy** | Heavy, Large, Industrial (size), Jumbo, Mega | heavy, large, jumbo, mega, oversized, high-capacity (size) |
| **Application — domestic** | Domestic, Home, Residential, Household, Consumer | domestic, home, home-use, residential, household, personal, consumer |
| **Application — industrial/commercial** | Industrial, Commercial, Professional, Bulk, Enterprise | industrial, commercial, professional, heavy-duty (application), bulk, factory, plant |
| **Target customer — children** | Kids, Children, Junior, Baby (customer), Infant, Toddler | kids, children, junior, baby (customer context), infant, toddler, child |
| **Target customer — women** | Women, Ladies, Female | women, ladies, female, woman's, for women |
| **Portability** | Portable, Mobile, Wireless, Cordless, Handheld | portable, mobile, wireless, cordless, handheld, battery-powered, on-the-go |
| **Certification / grade** | Food Grade, Medical Grade, ISI, BIS, Pharmaceutical Grade | food-safe, food-grade, FSSAI, medical-grade, hospital-grade, pharma-grade |

**Not subject to this rule (name collision rule handles these):** Material/Technology, Brand, Geographic origin/GI-tagged.

**Multi-dimension:** When multiple siblings trigger different dimensions simultaneously, all fire. Combined blocked set = union of all synonym clusters.

**Context-sensitivity:** Extend synonym clusters with product-category-specific synonyms (e.g. "purana" for used condition in heavy equipment). Generate 3–5 additional context-specific synonyms per triggered dimension.

**When a dimension triggers:**
1. Enhanced name (4w/5w/6w/long) containing a blocked term → DISCARD. Generate replacement.
2. Alt name containing blocked term → DISCARD. Omit (do not replace).
3. Set `segment_contamination_active: true`, output `segment_contamination_dimensions`.

**Exception — no sibling exists for a dimension:** Root may include terms for it. Set `segment_contamination_active: false`, write `segment_contamination_disclaimer`.

```
Example 1 — Condition fires: Root "JCB Backhoe Loader" / Sibling "Refurbished JCB"
  "Second Hand JCB Backhoe Loader" → DISCARD
  "JCB 3DX EcoXpert Backhoe Loader" → KEEP ✓

Example 2 — Children segment fires: Root "Swimming Pools" / Sibling "Kids Swimming Pools"
  "Baby Swimming Pool" → DISCARD (customer context)
  "Family Swimming Pool" → KEEP ✓ ("Family" ≠ children's segment)

Example 3 — Domestic + Industrial both fire: Root "Water Pumps"
  "Home Industrial Water Pump India" → DISCARD (two violations)
  "Monoblock Water Pump" → KEEP ✓
  "Agricultural Water Pump" → KEEP ✓ (no agricultural sibling)
```

**Step 2 — Name Collision Rule:**
Compare every candidate against Agent 4 related MCAT name list.
- Matches MCAT where `is_duplicate: yes` AND `to_be_merged: yes` → KEEP ✓
- Matches MCAT where either flag is `no` → DISCARD ✗ AND record in `alias_collision_merge_signals`

**Step 3 — 4 Enhanced Name Variants:**

| Variant | Word Count | Use Case |
|---|---|---|
| `enhanced_name_4w` | Exactly 4 words | Breadcrumb / tag label / compact UI |
| `enhanced_name_5w` | Exactly 5 words | Short heading / button label |
| `enhanced_name_6w` | Exactly 6 words | Section heading / card title |
| `enhanced_name_long` | 60–120 chars (hard max 160) | Long-tail SEO explainer |

Rules: Every word earns its place. No filler. Must NOT be "MCAT Name + one word". No seller terms (manufacturer, supplier). No city/location names.

```
MCAT: "FRP Swimming Pools"
  Keywords: fiberglass (5,650 impressions), readymade (1,006), terrace/rooftop (2,356)
  enhanced_name_4w:   "Fiberglass Prefabricated Swimming Pools"
  enhanced_name_5w:   "Readymade Fiberglass Pool for Homes"
  enhanced_name_6w:   "Readymade FRP Pools for Rooftop Terrace"
  enhanced_name_long: "Readymade Fiberglass Prefabricated Swimming Pools for Hotels,
                       Resorts, Homes and Rooftop Terrace Installation"

BAD:
  ✗ "FRP Swimming Pools Today"  (filler)
  ✗ "Buy FRP Pools Online Now"  (transactional filler)
  ✗ "FRP Swimming Pools Manufacturer Supplier India"  (seller/location terms)
```

**Step 4 — Up to 10 Alt Names:** Backed by keyword data. Buyer-search-intent language. Deduplicate spelling variants. No city/location or business-type variants. No blocked terms. No live related MCAT names.

**Output fields:**
`enhanced_name_4w/5w/6w/long`, `top_10_alt_names`, `segment_contamination_active`, `segment_contamination_dimensions`, `segment_contamination_disclaimer`, `alias_collision_merge_signals`

`alias_collision_merge_signals` format:
```json
[{"related_mcat_name": "", "colliding_candidate": "", "collision_type": "exact | semantic_equivalent",
  "signal_strength": "strong | moderate | weak", "rationale": ""}]
```

---

### Agent 14 — Pre-Cleaning Structural Verdict
**Runs:** Per-MCAT, Wave 3b.
**Role:** Makes the structural governance decision: dissolve, rename, merge, or clean?

**Inputs:** `vision_output` (Agent 3), Agent 4 slim output, Agent 8 `category_nature`, Agent 12 `alias_collision_merge_signals`

**The Four Structural Questions:**

| Question | Verdict | Decision Logic |
|---|---|---|
| Dissolve? | yes/no | `yes` only if `is_vague: yes` AND `is_thin: yes` AND no clean absorb target exists |
| Rename? | yes/no | `yes` only if name audit `verdict: incorrect` AND clearly superior name has significantly higher search volume |
| Merge into other? | yes/no | `yes` if `is_thin: yes` AND ≥70% product overlap with true parent/sibling, OR a parent MCAT carries `is_duplicate: yes, to_be_merged: yes` |
| Absorb others? | yes/no | `yes` for each MCAT where Agent 4 flags `is_duplicate: yes` AND `to_be_merged: yes`. Brand MCATs never here. |

**Merge Signal Evaluation (per related MCAT):**

| Signal | Fires when | Weight |
|---|---|---|
| **S1 — Thin Bifurcation** | Related MCAT `is_thin: yes` AND name describes type already covered by root | Independently sufficient if buyer confirms |
| **S2 — Semantic Equivalence** | Related MCAT name = direct synonym of root | Independently sufficient |
| **S3 — Name Alias Collision** | `alias_collision_merge_signals` contains this MCAT | Strong corroborating |
| **S4 — Buyer-Search Funnel Collapse** | >60% supplier overlap AND `is_thin: yes` AND no distinct buyer intent | Independently sufficient when all three fire |
| **S5 — Weak Standalone Nature** | `is_thin: yes` OR `is_vague: yes` while root is healthy | Corroborating |
| **S6 — High Product Overlap** | Product overlap >70% AND low standalone differentiation | Corroborating |

**Buyer-First Judgment Rule for S1:** "If absorbed, would ANY buyer lose a meaningful navigation destination?" NO → confirm merge. YES → keep separate.

**Brand MCAT guard:** Before writing `mcats_to_absorb`, test each candidate: anchored to a commercial brand name? YES → remove, override to `is_duplicate: no, to_be_merged: no`, flag error.

**Parent direct-match merge check:** If any `parent_category` MCAT carries `is_duplicate: yes, to_be_merged: yes` → set `merge_into_other: yes` and `merge_into_other_target` = that parent.

---

### Consolidator — Two-File Builder
**Runs:** Per-MCAT, Wave 4.
**Role:** Assembles all agent outputs into two deliverable JSON files.

**Assembly Rules — `context.json`:**

**Rule 0a — `data_quality_flags`:** Check if Agents 2, 7, or 10 set `input_data_absent: true`. If yes, write `data_quality_flags`. If no, omit field entirely.

**Rule 0 — `mcat_description`:** From Agent 3. **Segment contamination filter (mandatory):** If Agent 12 `segment_contamination_active: true`, iterate over all `segment_contamination_dimensions`. Remove any `product_types` or `buyer_segments` entry containing a blocked term.

**Rule 1 — `gating_flags`:** From Agents 4, 6, 7, 9, 11. `company_important` from Agent 11 overwrites Agent 6 placeholder. `biz_exception` from Agent 9 refined by Agent 11 `authorised_dealer_brand_exception`. `ocr` + `ocr_note` from Agent 7. `buyer_attracting_attributes` + `show_spec_on_listing` from Agent 6.

**Rule 1a — `category_nature`:** From Agent 8. Immediately after `gating_flags`.

**Rule 2 — `structural_verdict`:** From Agent 14. Includes `thumbnail_audit` (from Agent 5, nested here).

**Rule 3 — `names_aliases`:** 
1. Final name collision check: drop any enhanced name or alt name matching a live related MCAT where `is_duplicate ≠ yes` OR `to_be_merged ≠ yes`
2. Segment contamination filter on `search_queries`: remove any query containing a blocked term from any active `segment_contamination_dimensions`
3. Write `segment_contamination_disclaimer` only when Agent 12's value is non-null

**Rule 4 — `relevant_photos`, `thin_photos`, `irrelevant_photos`:** From Agent 7. Source hierarchy: Agent 2 verified images (highest priority) → Agent 3 raw_images → web search. Refuse to write photo examples if Agent 10 has not confirmed real page URLs. When `input_data_absent: true`, flag accordingly.

**Rule 5 — `relevant_titles`, `thin_titles`, `irrelevant_titles`:** From Agent 10. `irrelevant_titles` = actively wrong tokens only. `thin_titles` = correct but incomplete. Never mixed.

**Rule 6 — `wrong_mcat_classifier`:** From Agent 10 + Agent 4 routing notes. Every class names a specific target MCAT.

**Rule 7 — `few_shot_examples`:** From Agent 10. Real listings only. Polar extremes only. 4-value `verdict` enum.

**Rule 8 — `mcat_thumbnail_images`:** From Agent 5. 3 entries. Primary segment only if `needs_cleaning: yes`.

**Rule 9 — `related_mcats_summary`:** Lean index from Agent 4. Per related MCAT: `{mcat_name, relationship, is_duplicate}` only.

**Rule 10 — `missing_data_fallbacks`:** HIGH importance fields → `confidence_cap: "medium"` when missing. LOW → null.

**Assembly Rules — `related_mcat_context.json`:**
1. Root MCAT identity header
2. `related_mcats` — full Agent 4 output. All entries including `unrelated`.
3. `merge_summary` — from Agent 14 `structural_verdict.mcats_to_absorb`
4. `alias_collision_merge_signals` — from Agent 12

---

## Output Schema 1: `context.json`

```json
{
  "mcat_id": 0,
  "mcat_name": "",
  "version": "1.0",
  "generated": "YYYY-MM-DD",
  "pipeline_version": "v5.9",
  "page_url": "",

  "data_quality_flags": {
    "input_data_absent": true,
    "affected_fields": []
  },

  "mcat_description": {
    "short": "1–2 sentence plain-English definition.",
    "long": "4-sentence max. No price figures.",
    "product_types": [],
    "primary_applications": [],
    "buyer_segments": []
  },

  "gating_flags": {
    "use_photo": true,
    "use_specs": true,
    "photo_weight": "HIGH | MEDIUM | LOW",
    "isq_important": "High | Medium | Low",
    "company_important": "High | Medium | Low",
    "price_important": "High | Medium | Low",
    "unit_important": "High | Low",
    "canonical_unit": "",
    "canonical_unit_note": "",
    "hyperlocal": "All India | <state/region>",
    "biz_exception": false,
    "location_exception": false,
    "ocr": false,
    "ocr_note": "",
    "buyer_attracting_attributes": [],
    "show_spec_on_listing": true,
    "reason": "Max 3 sentences. One sentence per flag cluster."
  },

  "category_nature": {
    "is_generic": "yes | no",
    "is_specific": "yes | no",
    "is_vague": "yes | no",
    "is_thin": "yes | no",
    "is_branded": "yes | no",
    "is_service": "yes | no",
    "reason": "2-bullet justification."
  },

  "structural_verdict": {
    "dissolve": "yes | no",
    "rename": "yes | no",
    "rename_to": "null | string",
    "merge_into_other": "yes | no",
    "merge_into_other_target": "null | string",
    "absorb_others_into_this": "yes | no",
    "mcats_to_absorb": [
      {
        "mcat_name": "",
        "total_products": 0,
        "total_suppliers": 0,
        "common_products_with_root": 0,
        "merge_complexity": "low | medium | high",
        "category_nature_tags": {
          "is_generic": "", "is_specific": "", "is_vague": "",
          "is_thin": "", "is_branded": "", "is_service": ""
        },
        "merge_signals_fired": ["S1 — Thin Bifurcation"],
        "buyer_navigation_loss": "none | minimal | significant",
        "reason": "2–3 bullets: signals fired, navigation impact, post-absorption plan."
      }
    ],
    "proceed_to_cleaning": "yes | no",
    "cleaning_blocks_on_structural": false,
    "thumbnail_audit": {
      "current_thumbnail_correct": true,
      "reason": ["• visual evidence bullet", "• compliance with image type criteria"]
    },
    "summary": "Max 5 bullets: (1) dissolve/rename/merge verdict, (2) each absorb candidate with signals + navigation loss, (3) proceed_to_cleaning gate."
  },

  "names_aliases": {
    "canonical": "",
    "enhanced_names": {
      "4w": "",
      "5w": "",
      "6w": "",
      "long": ""
    },
    "aliases": [],
    "segment_contamination_disclaimer": "null | string",
    "search_queries": [
      {"query": "", "type": "Exact MCAT Name | Category-Specific | Material-Specific | Price-Intent | Segment-Specific | Application-Specific | Type-Specific | Generic"}
    ]
  },

  "relevant_photos": {
    "summary": "One sentence: what a correct listing image looks like.",
    "product_identity": [],
    "acceptable_scenes": [],
    "examples": [
      {"photo_url": "", "listing_title": "", "item_id": "", "reason": "", "source": "verified_good | page_browse_only | web_search"}
    ]
  },

  "thin_photos": {
    "summary": "One sentence: correct product but insufficient buyer-useful detail.",
    "thinness_signals": [],
    "examples": []
  },

  "irrelevant_photos": {
    "summary": "One sentence: most common actively-wrong image failure. NOT low quality.",
    "failure_classes": [
      {
        "class": "",
        "description": "",
        "examples": [],
        "detection_signal": "Signal must identify a wrong/contaminating visual element PRESENT.",
        "failure_mode": "wrong_product | wrong_material | seller_watermark_obstruction | unfinished_product | spec_sheet_used",
        "action": ""
      }
    ]
  },

  "relevant_titles": {
    "summary": "One sentence: what a strong title looks like.",
    "strong_positive_signals": [],
    "structural_patterns": [],
    "examples": {"extreme_good": [], "acceptable": []}
  },

  "thin_titles": {
    "summary": "Titles correct but incomplete — flag as thin, not violations.",
    "thinness_signals": [],
    "examples": []
  },

  "irrelevant_titles": {
    "summary": "Titles with actively wrong/contaminating tokens only.",
    "failure_classes": [
      {
        "class": "",
        "signal": "One sentence — wrong token PRESENT.",
        "failure_mode": "location_noise | business_type_noise | ambiguous_material | wrong_product | misleading_claim",
        "rule": "",
        "examples": []
      }
    ]
  },

  "wrong_mcat_classifier": {
    "description": "",
    "input_data_absent": false,
    "classes": [
      {"class": "", "signal": "One sentence.", "examples": [], "correct_mcat": "Specific MCAT name — never vague"}
    ]
  },

  "few_shot_examples": [
    {
      "id": 1,
      "label": "CORRECT | INCORRECT — brief reason",
      "verdict": "correct | incorrect | incorrect_title | incorrect_specs",
      "input": {
        "title": "", "specs": {}, "photo_description": "", "price": "",
        "listing_url": "https://www.indiamart.com/proddetail/..."
      },
      "output": {
        "product_category": "not_outlier | outlier",
        "product_category_reason": "Only when outlier — wrong thing PRESENT",
        "title_vs_spec": "not_outlier | outlier",
        "title_vs_spec_reason": "Only when outlier",
        "contradiction_in_specs": "not_outlier | outlier",
        "contradiction_in_specs_reason": "Only when outlier",
        "photo_vs_title": "not_outlier | outlier",
        "photo_vs_title_reason": "Only when outlier",
        "photo_vs_spec": "not_outlier | outlier",
        "photo_vs_spec_reason": "Only when outlier",
        "photo_vs_category": "not_outlier | outlier",
        "photo_vs_category_reason": "Only when outlier",
        "suggested_category": "", "confidence": "high | medium | low",
        "flag": "null | wrong_mcat | spec_contradiction | location_contamination | biz_type_contamination"
      },
      "why_good": "For correct examples only",
      "correction": "For incorrect_title examples only"
    }
  ],

  "mcat_thumbnail_images": [
    {
      "id": 1,
      "description": "Detailed visual description.",
      "rationale": "Max 2 sentences.",
      "prompt_for_generation": "Text-to-image generation prompt.",
      "watermark": {"position": "bottom-right", "text": "IndiaMART AI", "applied": true}
    }
  ],

  "related_mcats_summary": [
    {"mcat_name": "", "relationship": "parent_category | sibling_category | cross_sell | upsell | downsell | accessory | parts | service | substitute | unrelated", "is_duplicate": "yes | no"}
  ],

  "missing_data_fallbacks": [
    {"missing_field": "", "checks_to_skip": [], "return_value": "skipped", "confidence_cap": "medium | low | null", "flag": "null | flag_name", "note": ""}
  ],

  "seller_pdfs": {
    "pdf_count_processed": 0,
    "agent1_pdf_supplement": []
  },
  "buyleads": null
}
```

---

## Output Schema 2: `related_mcat_context.json`

```json
{
  "mcat_id": 0,
  "mcat_name": "",
  "generated": "YYYY-MM-DD",
  "pipeline_version": "v5.9",
  "page_url": "",
  "file_purpose": "Taxonomy governance — related MCAT classification, overlap data, and merge analysis. Used by category management teams. Not loaded by the listing audit AI.",

  "related_mcats": [
    {
      "mcat_name": "", "mcat_id": 0, "url": "",
      "is_brand_mcat": "yes | no",
      "relationship": "super_parent | parent_category | sibling_category | brand_mcat | cross_sell | upsell | downsell | accessory | parts | service | substitute | unrelated",
      "sibling_bifurcation_type": "material | brand | technology | application | condition | form_factor | capacity_size | fuel_energy | segment | specification | output_type | geographic | composite | null",
      "direction": "bidirectional | from_this | from_that_into_this",
      "reason": "2-bullet buyer-perspective justification citing overlap data.",
      "is_duplicate": "yes | no", "to_be_merged": "yes | no", "is_overlapping": "yes | no",
      "overlap_with_root": {"common_products": 0, "common_suppliers": 0, "product_overlap_pct": 0.0, "supplier_overlap_pct": 0.0},
      "total_products": 0, "total_suppliers": 0,
      "merge_signals_fired": [],
      "category_nature": {
        "is_generic": "", "is_specific": "", "is_vague": "", "is_thin": "", "is_branded": "", "is_service": "",
        "reason": "2–3 bullet justification."
      },
      "routing_note": "When to route TO this MCAT; when to route FROM it back here."
    }
  ],

  "merge_summary": {
    "absorb_others_into_this": "yes | no",
    "mcats_to_absorb": [
      {
        "mcat_name": "", "total_products": 0, "total_suppliers": 0, "common_products_with_root": 0,
        "merge_complexity": "low | medium | high",
        "category_nature_tags": {},
        "merge_signals_fired": [],
        "buyer_navigation_loss": "none | minimal | significant",
        "reason": "2–3 bullets."
      }
    ],
    "merge_into_other": "yes | no",
    "merge_into_other_target": "MCAT name | null"
  },

  "alias_collision_merge_signals": [
    {
      "related_mcat_name": "", "colliding_candidate": "",
      "collision_type": "exact | semantic_equivalent",
      "signal_strength": "strong | moderate | weak",
      "rationale": ""
    }
  ]
}
```
