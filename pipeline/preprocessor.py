"""
Catalogue Preprocessor — pure Python, zero LLM cost.
Filters ~98K MCAT catalogue to a scored candidate list for one root MCAT.
Implements all 6 steps from SKILL-v6_3.md.
"""
import re
import csv
from typing import List, Dict
from rapidfuzz import fuzz

# ── Step 4: Synonym map ──────────────────────────────────────────────────
SYNONYM_MAP = {
    "frp": ["fiberglass", "fibreglass", "grp"],
    "fiberglass": ["frp", "fibreglass", "grp"],
    "fibreglass": ["frp", "fiberglass", "grp"],
    "grp": ["frp", "fiberglass", "fibreglass"],
    "pool": ["swimming pool", "pools"],
    "pools": ["swimming pool", "pool"],
    "prefab": ["readymade", "modular", "portable", "prefabricated"],
    "readymade": ["prefab", "modular", "portable", "prefabricated"],
    "modular": ["prefab", "readymade", "portable"],
    "portable": ["prefab", "readymade", "modular"],
    "inflatable": ["blow up", "air filled", "pvc inflatable"],
    "pump": ["pumps", "motor pump"],
    "pumps": ["pump", "motor pump"],
    "tank": ["tanks", "storage tank"],
    "tanks": ["tank", "storage tank"],
    "pipe": ["pipes", "piping", "tube"],
    "pipes": ["pipe", "piping", "tube"],
    "machine": ["machines", "machinery", "equipment"],
    "machines": ["machine", "machinery", "equipment"],
    "valve": ["valves"],
    "valves": ["valve"],
    "filter": ["filters", "filtration"],
    "filters": ["filter", "filtration"],
    "heater": ["heaters", "heating"],
    "heaters": ["heater", "heating"],
    "cover": ["covers", "covering"],
    "covers": ["cover", "covering"],
    "chemical": ["chemicals"],
    "chemicals": ["chemical"],
    "tile": ["tiles", "tiling"],
    "tiles": ["tile", "tiling"],
    "light": ["lights", "lighting"],
    "lights": ["light", "lighting"],
    "mat": ["mats", "matting"],
    "mats": ["mat", "matting"],
    "net": ["nets", "netting"],
    "nets": ["net", "netting"],
    "ladder": ["ladders", "step ladder"],
    "ladders": ["ladder", "step ladder"],
    "slide": ["slides", "water slide"],
    "slides": ["slide", "water slide"],
    "toy": ["toys"],
    "toys": ["toy"],
    "kids": ["children", "children's", "kid"],
    "children": ["kids", "kid", "children's"],
    "swimming": ["swim"],
    "swim": ["swimming"],
    "water": ["aqua"],
    "aqua": ["water"],
    "jacuzzi": ["hot tub", "spa bath", "whirlpool"],
    "spa": ["jacuzzi", "hot tub"],
    "fountain": ["fountains", "water fountain"],
    "fountains": ["fountain", "water fountain"],
}

STOP_WORDS = {
    "a", "an", "the", "and", "or", "of", "for", "in", "on", "at", "to",
    "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "its", "it", "this", "that", "these", "those", "all", "any", "each",
    "&", "-", "/",
}


def tokenise(name: str) -> List[str]:
    """Step 1: Tokenise name, strip stop words."""
    tokens = re.findall(r"[a-zA-Z0-9]+", name.lower())
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]


def keyword_match_score(root_tokens: List[str], candidate_name: str,
                        root_name_lower: str) -> float:
    """Step 2: Keyword overlap scoring."""
    cand_lower = candidate_name.lower().strip()

    # Exact full-name match
    if cand_lower == root_name_lower:
        return 1.0

    cand_tokens = set(tokenise(candidate_name))
    root_set = set(root_tokens)

    if not root_set or not cand_tokens:
        return 0.0

    overlap = root_set & cand_tokens
    overlap_ratio = len(overlap) / len(root_set)

    if overlap_ratio == 1.0:
        return 0.9
    elif overlap_ratio >= 0.5:
        return 0.7
    elif overlap_ratio > 0:
        return 0.4
    return 0.0


def fuzzy_similarity_boost(root_name: str, candidate_name: str) -> float:
    """Step 3: Fuzzy string similarity weighted at 0.3."""
    score = fuzz.token_sort_ratio(root_name.lower(), candidate_name.lower())
    return (score / 100.0) * 0.3


def synonym_boost(root_tokens: List[str], candidate_name: str) -> float:
    """Step 4: Synonym expansion check."""
    cand_tokens = set(tokenise(candidate_name))
    for rt in root_tokens:
        synonyms = SYNONYM_MAP.get(rt, [])
        for syn in synonyms:
            syn_tokens = set(tokenise(syn))
            if syn_tokens & cand_tokens:
                return 0.2
    return 0.0


def pre_label(root_tokens: List[str], root_name_lower: str,
              candidate_name: str, score: float) -> Dict:
    """Step 6: Pre-label with relevance, relationship, note."""
    cand_lower = candidate_name.lower().strip()
    cand_tokens = set(tokenise(candidate_name))
    root_set = set(root_tokens)

    # Relevance
    overlap = root_set & cand_tokens
    has_synonym = synonym_boost(root_tokens, candidate_name) > 0
    if score >= 0.7 or has_synonym:
        relevance = "high"
    elif score >= 0.4:
        relevance = "medium"
    else:
        relevance = "low"

    # Relationship
    if root_name_lower in cand_lower and root_name_lower != cand_lower:
        relationship = "likely_child"
    elif cand_lower in root_name_lower and root_name_lower != cand_lower:
        relationship = "likely_parent"
    elif overlap and any(t for t in overlap
                         if not t.isdigit() and len(t) > 2):
        relationship = "likely_sibling"
    else:
        relationship = "unknown"

    # Note
    if overlap:
        note = f"Token match: {', '.join(sorted(overlap))}"
    elif has_synonym:
        note = "Synonym match"
    else:
        note = "Fuzzy match only"

    return {
        "pre_relevance": relevance,
        "pre_relationship": relationship,
        "pre_note": note,
    }


def run_preprocessor(all_mcats_path: str, root_mcat_name: str,
                     root_mcat_id: str) -> List[Dict]:
    """
    Main preprocessor entry point.
    Returns list of candidate dicts (top 100).
    """
    root_tokens = tokenise(root_mcat_name)
    root_name_lower = root_mcat_name.lower().strip()

    if not root_tokens:
        return []

    # Read all MCATs
    candidates = []
    try:
        with open(all_mcats_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cand_id = row.get("glcat_mcat_id", "").strip()
                cand_name = row.get("glcat_mcat_name", "").strip()
                if not cand_name or cand_id == str(root_mcat_id):
                    continue

                # Step 2: keyword match
                kw_score = keyword_match_score(root_tokens, cand_name, root_name_lower)
                if kw_score == 0.0:
                    # Quick synonym check before discarding
                    syn_score = synonym_boost(root_tokens, cand_name)
                    if syn_score == 0.0:
                        continue
                    kw_score = 0.3  # minimum for synonym match

                # Step 3: fuzzy similarity
                fuzzy_score = fuzzy_similarity_boost(root_mcat_name, cand_name)

                # Step 4: synonym boost
                syn_score = synonym_boost(root_tokens, cand_name)

                # Composite score
                final_score = min(kw_score + fuzzy_score + syn_score, 1.0)

                # Step 5: threshold
                if final_score < 0.3:
                    continue

                # Step 6: pre-label
                labels = pre_label(root_tokens, root_name_lower, cand_name, final_score)

                candidates.append({
                    "root_mcat_id": str(root_mcat_id),
                    "root_mcat_name": root_mcat_name,
                    "candidate_mcat_id": cand_id,
                    "candidate_mcat_name": cand_name,
                    "similarity_score": round(final_score, 4),
                    **labels,
                })
    except Exception as e:
        print(f"  ⚠ Preprocessor error reading {all_mcats_path}: {e}")
        return []

    # Sort descending, cap at 100
    candidates.sort(key=lambda x: x["similarity_score"], reverse=True)
    return candidates[:100]


def save_preprocessed(candidates: List[Dict], output_path: str):
    """Save preprocessed candidates to CSV."""
    if not candidates:
        return
    fieldnames = [
        "root_mcat_id", "root_mcat_name", "candidate_mcat_id",
        "candidate_mcat_name", "similarity_score", "pre_relevance",
        "pre_relationship", "pre_note"
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(candidates)
