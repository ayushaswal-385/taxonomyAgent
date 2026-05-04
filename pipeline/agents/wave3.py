"""Wave 3 agents: Agent 12 (Name Generator) and Agent 14 (Structural Verdict)."""
import json

def run_agent_12(client, mcat_name, mcat_id, vision_output, agent4_slim):
    """Agent 12 — Name Generator (Wave 3a)."""
    system = f"""You are Agent 12 — Name Generator for "{mcat_name}" (ID: {mcat_id}).
Produce 4 enhanced name variants, up to 10 alt names, alias_collision_merge_signals, and segment contamination output.

Step 1 — Segment Contamination: Scan Agent 4 siblings for trigger words across 9 dimensions:
Condition(used/refurbished), Size-small(mini/compact), Size-large(heavy/industrial), Application-domestic, Application-industrial, Customer-children(kids), Customer-women, Portability(portable/wireless), Certification(food-grade/medical-grade).
When triggered: DISCARD any enhanced/alt name containing blocked terms.

Step 2 — Name Collision Rule: Compare candidates against Agent 4 related MCAT names.
Match + is_duplicate:yes AND to_be_merged:yes → KEEP. Otherwise → DISCARD + record in alias_collision_merge_signals.

Step 3 — 4 Enhanced Names:
- enhanced_name_4w: Exactly 4 words (breadcrumb/tag)
- enhanced_name_5w: Exactly 5 words (short heading)
- enhanced_name_6w: Exactly 6 words (section heading)
- enhanced_name_long: 60-120 chars (long-tail SEO)
Rules: Every word earns its place. No filler. No seller terms. No city/location.

Step 4 — Up to 10 Alt Names: Backed by keyword data. Buyer-search-intent language.

RESPOND WITH ONLY VALID JSON:
{{"enhanced_name_4w":"","enhanced_name_5w":"","enhanced_name_6w":"","enhanced_name_long":"",
"top_10_alt_names":[""],
"segment_contamination_active":false,
"segment_contamination_dimensions":[],
"segment_contamination_disclaimer":null,
"alias_collision_merge_signals":[{{"related_mcat_name":"","colliding_candidate":"","collision_type":"exact|semantic_equivalent","signal_strength":"strong|moderate|weak","rationale":""}}]}}"""

    kw_data = json.dumps({k: v for k, v in vision_output.items()
                           if k in ["top_internal_keywords", "top_google_keywords", "alt_names", "mcat_description", "listing_quality"]}, indent=1) if vision_output else "{}"
    slim = json.dumps(agent4_slim[:30], indent=1) if agent4_slim else "[]"

    user = f"""MCAT: {mcat_name} (ID: {mcat_id})

Agent 3 keyword and context data:
{kw_data}

Agent 4 slim output (related MCATs):
{slim}

Generate names following all rules. Check segment contamination and name collisions."""

    result = client.call("Agent_12_Names", mcat_name, system, user, max_tokens=4000)
    return result.get("content", {})


def run_agent_14(client, mcat_name, mcat_id, vision_output, agent4_slim, agent8_output, agent12_output):
    """Agent 14 — Pre-Cleaning Structural Verdict (Wave 3b)."""
    system = f"""You are Agent 14 — Pre-Cleaning Structural Verdict for "{mcat_name}" (ID: {mcat_id}).
Make the structural governance decision: dissolve, rename, merge, or clean?

Four Structural Questions:
1. Dissolve? yes only if is_vague:yes AND is_thin:yes AND no clean absorb target
2. Rename? yes only if name audit verdict:incorrect AND superior name has higher search volume
3. Merge into other? yes if is_thin:yes AND ≥70% overlap with parent/sibling
4. Absorb others? yes for each with is_duplicate:yes AND to_be_merged:yes. Brand MCATs NEVER here.

Merge Signal Evaluation per related MCAT:
S1-Thin Bifurcation, S2-Semantic Equivalence, S3-Name Alias Collision, S4-Buyer-Search Funnel Collapse, S5-Weak Standalone Nature, S6-High Product Overlap

Brand MCAT guard: Never absorb brand MCATs.
proceed_to_cleaning: yes unless structural changes block it.

RESPOND WITH ONLY VALID JSON:
{{"dissolve":"yes|no","rename":"yes|no","rename_to":null,
"merge_into_other":"yes|no","merge_into_other_target":null,
"absorb_others_into_this":"yes|no",
"mcats_to_absorb":[{{"mcat_name":"","total_products":0,"total_suppliers":0,"common_products_with_root":0,"merge_complexity":"low|medium|high","category_nature_tags":{{"is_generic":"","is_specific":"","is_vague":"","is_thin":"","is_branded":"","is_service":""}},"merge_signals_fired":[],"buyer_navigation_loss":"none|minimal|significant","reason":"2-3 bullets"}}],
"proceed_to_cleaning":"yes|no","cleaning_blocks_on_structural":false,
"summary":"Max 5 bullets"}}"""

    cat_nature = json.dumps(agent8_output, indent=1) if agent8_output else "{}"
    collision = json.dumps(agent12_output.get("alias_collision_merge_signals", []), indent=1) if agent12_output else "[]"
    slim = json.dumps(agent4_slim[:30], indent=1) if agent4_slim else "[]"
    listing_q = json.dumps(vision_output.get("listing_quality", {}), indent=1) if vision_output else "{}"

    user = f"""MCAT: {mcat_name} (ID: {mcat_id})

Agent 3 listing_quality: {listing_q}
Agent 4 slim output: {slim}
Agent 8 category_nature: {cat_nature}
Agent 12 alias_collision_merge_signals: {collision}

Make the structural verdict. Evaluate all merge signals for each candidate."""

    result = client.call("Agent_14_Verdict", mcat_name, system, user, max_tokens=5000)
    return result.get("content", {})
