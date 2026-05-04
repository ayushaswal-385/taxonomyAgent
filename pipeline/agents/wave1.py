"""Agent 3 — Context Extraction + Market Research + Listing Quality Check (Wave 1)."""
import json
from pipeline.web_fetcher import fetch_page


def run_agent_03(client, mcat_name, mcat_id, mcat_url,
                 google_kws, internal_kws, agent1_output, call_data,
                 taxonomy_context=None):
    """Agent 3 — Foundation agent. All Wave 2 agents depend on this.

    taxonomy_context: dict from agent4_input.json — passed by orchestrator.
    Agent 3 appends it UNCHANGED to vision_output so all Wave 2+ agents can read it.
    """

    # Fetch MCAT page
    page_data = fetch_page(mcat_url) if mcat_url else {"text": "", "title": "", "error": "no_url"}

    # Prepare keyword summaries (top 15 each)
    gkw_text = ""
    if google_kws:
        for kw in google_kws[:15]:
            gkw_text += (f"  {kw.get('Query','')}: clicks={kw.get('Clicks','')}, "
                         f"impressions={kw.get('Impressions','')}, "
                         f"pos={kw.get('Avg of Avg Position','')}\n")

    ikw_text = ""
    if internal_kws:
        for kw in internal_kws[:15]:
            ikw_text += (f"  {kw.get('keyword','')}: pageviews={kw.get('Pageviews','')}, "
                         f"pdp_clicks={kw.get('PDP Clicks','')}, "
                         f"calls={kw.get('Calls','')}, ctr={kw.get('CTR','')}\n")

    # PDF supplement
    pdf_text = ""
    if agent1_output and agent1_output.get("pdf_summary"):
        supp = agent1_output["pdf_summary"].get("agent1_pdf_supplement", [])
        if supp:
            pdf_text = (f"\nPDF Supplement ({len(supp)} products identified for this category):\n"
                        f"{json.dumps(supp[:10], indent=2)}")

    # Call data
    call_text = ""
    if call_data:
        call_text = f"\nBuyer Call Data ({len(call_data)} rows):\n"
        for row in call_data[:20]:
            call_text += (f"  Product: {row.get('product_name','')}, "
                          f"Amount: {row.get('amount','')}, "
                          f"Spec: {row.get('spec_name','')}: "
                          f"{row.get('spec_value','')} {row.get('spec_unit','')}\n")

    # Taxonomy context block for prompt (anchor market research to correct domain)
    taxonomy_block = ""
    if taxonomy_context:
        parent_info = taxonomy_context.get("parent") or {}
        taxonomy_block = (
            f"\n=== TAXONOMY CONTEXT (from preprocessor — use to anchor research) ===\n"
            f"Full path: {taxonomy_context.get('full_path', 'N/A')}\n"
            f"MCAT Level: {taxonomy_context.get('mcat_level', 'N/A')}\n"
            f"Listing Count: {taxonomy_context.get('listing_count', 'N/A')}\n"
            f"Parent MCAT: {parent_info.get('name', 'N/A')} (level {parent_info.get('level', 'N/A')})\n"
            f"Direct Siblings: {taxonomy_context.get('direct_sibling_count', 0)}\n"
            f"Indirect Siblings: {taxonomy_context.get('indirect_sibling_count', 0)}\n"
            f"Use mcat_level and listing_count as hard anchors (do NOT estimate from page tiles)."
        )

    system = f"""You are Agent 3 — Context Extraction + Market Research + Listing Quality Check.
You are the FOUNDATION agent. All subsequent agents depend on your output.
MCAT: "{mcat_name}" (ID: {mcat_id})

Execute these steps:
1. Analyse the MCAT page content provided
2. Listing Quality Check: "If a buyer searched for {mcat_name} and landed on this page, would ALL visible listings make sense?"
   - Mixed segments (industrial+domestic) → needs_cleaning: yes
   - Ambiguous name attracting different buyer types → needs_cleaning: yes
   - Price range >2 orders of magnitude due to segment mixing (not size variation) → needs_cleaning: yes
   - All listings same product family, same buyer intent → needs_cleaning: no
3. External market context (based on your knowledge of Amazon India, Google Shopping, manufacturer sites)
4. Parse keyword data provided
5. Integrate PDF supplement if provided (supplements, doesn't override page data)
6. Integrate call data if provided (buyer vocabulary supplement only — do NOT extract specs)
7. Record raw listings and images from page

IMPORTANT: Your JSON output MUST include a "taxonomy_context" field — pass the taxonomy_context
you received UNCHANGED. All downstream agents read it from your output.

RESPOND WITH ONLY VALID JSON:
{{
  "mcat_description": {{
    "short": "1-2 sentence definition",
    "long": "4-sentence max expert description. No price figures.",
    "product_types": ["list of distinct product types/variants"],
    "primary_applications": ["real-world use cases"],
    "buyer_segments": ["who buys and in what context"]
  }},
  "listing_quality": {{
    "needs_cleaning": "yes|no",
    "reason": "2-bullet explanation",
    "primary_segment": "name of primary segment when needs_cleaning=yes, else null"
  }},
  "price_range": "observed price band string",
  "alt_names": ["alternate names from page + market + call data"],
  "top_internal_keywords": [{{"keyword":"","pageviews":0,"pdp_clicks":0,"calls":0}}],
  "top_google_keywords": [{{"query":"","clicks":0,"impressions":0,"avg_position":0}}],
  "market_context": "external market naming norms, price tiers",
  "page_metadata": {{"title":"","meta_desc":"","meta_keywords":"","h1":""}},
  "thumbnail_image_description": "description of current MCAT thumbnail",
  "raw_listings": [{{"title":"","price":"","specs_snippet":"","image_url":"","proddetail_url":""}}],
  "raw_images": [{{"url":"","listing_context":""}}],
  "call_data_buyer_vocabulary": ["distinct buyer terms from call data"],
  "call_data_context_note": "1-2 sentences on call data insights",
  "taxonomy_context": {{}}
}}"""

    user = f"""MCAT: {mcat_name} (ID: {mcat_id})
Page URL: {mcat_url}
{taxonomy_block}

=== MCAT PAGE CONTENT ===
Title: {page_data.get('title', '')}
{page_data.get('text', '')[:15000]}

=== GOOGLE SEARCH KEYWORDS (top 15) ===
{gkw_text if gkw_text else 'No data'}

=== INTERNAL SEARCH KEYWORDS (top 15) ===
{ikw_text if ikw_text else 'No data'}
{pdf_text}
{call_text}

Analyse this MCAT comprehensively. Perform the listing quality check. Build the full context.
Remember: include "taxonomy_context" in your output JSON (pass it through unchanged)."""

    result = client.call("Agent_03_Context", mcat_name, system, user, max_tokens=8000)
    content = result.get("content", {})
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            content = {"error": "parse_failed", "raw": content[:500]}

    # Ensure taxonomy_context is in output regardless of what the LLM returned
    # The orchestrator passes it; we guarantee it's present for downstream agents.
    if taxonomy_context is not None and isinstance(content, dict):
        content["taxonomy_context"] = taxonomy_context

    return content
