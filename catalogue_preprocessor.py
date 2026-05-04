"""
catalogue_preprocessor.py  —  v3.0
====================================
Runs per-MCAT in the Pre-Wave, before any agent.
Zero API calls. Pure Python.

Produces a single agent4_input.json per MCAT containing:
  - taxonomy_context       : full ancestry from tree
  - candidates[]           : merged, deduped pool with source_flags
  - family_context_pairs[] : sibling-sibling overlap pairs (Source C)

Candidate sources (all contribute, deduplicated by mcat_id):
  Tier 1a — direct siblings    : same immediate PMCAT
  Tier 1b — indirect siblings  : grandparent PMCAT children,
                                  only when immediate PMCAT is under another PMCAT
  Tier 2  — overlap confirmed  : all root pairs in related_mcats_overlap.csv
  Tier 3  — platform links     : all rows in mcat_related_categories.csv for root
  Tier 4  — semantic           : all score >= 0.7 from all_mcats_indiamart.csv
                                  (no cap — all high-confidence matches included)

Startup (once):
  startup(all_mcats, tree, overlap, platform)

Per-MCAT (inside orchestrator loop):
  preprocess(mcat_id, mcat_name, output_dir)

CLI:
  python catalogue_preprocessor.py \
      --mcat_id 30860 --mcat_name "Inflatable Swimming Pool" \
      --all_mcats all_mcats_indiamart.csv \
      --tree taxonomy_tree.csv \
      --overlap related_mcats_overlap.csv \
      --platform mcat_related_categories.csv \
      --output_dir output/
"""

import argparse
import csv
import json
import os
import re
from pathlib import Path
from collections import defaultdict

try:
    from rapidfuzz import fuzz as _fuzz
    def fuzzy_score(a: str, b: str) -> float:
        return _fuzz.token_sort_ratio(a, b) / 100.0
except ImportError:
    def fuzzy_score(a: str, b: str) -> float:
        def bigrams(s):
            s = s.lower()
            return set(s[i:i+2] for i in range(len(s)-1))
        ba, bb = bigrams(a), bigrams(b)
        if not ba or not bb: return 0.0
        return 2*len(ba & bb)/(len(ba)+len(bb))


# ══════════════════════════════════════════════════════════════════════════════
STOP_WORDS = {
    "a","an","and","are","as","at","be","by","for","from","has","he",
    "in","is","it","its","of","on","that","the","to","was","were","will",
    "with","&","or","but","not","also","all","both","per","type","types",
    "product","products","item","items","set","sets","buy","online","india",
    "price","supplier","manufacturer","exporter","wholesale","oem",
    "high","quality","best","new","used","second","hand"
}

SYNONYM_MAP: dict[str, list[str]] = {
    "frp":        ["fiberglass","fibreglass","grp"],
    "fiberglass": ["frp","fibreglass","grp"],
    "fibreglass": ["frp","fiberglass","grp"],
    "grp":        ["frp","fiberglass","fibreglass"],
    "pool":       ["swimming pool","pools"],
    "pools":      ["swimming pool","pool"],
    "prefab":     ["readymade","modular","portable"],
    "readymade":  ["prefab","modular","portable"],
    "hdpe":       ["high density polyethylene"],
    "ms":         ["mild steel"],
    "gi":         ["galvanized iron","galvanised iron"],
    "ss":         ["stainless steel"],
    "pvc":        ["polyvinyl chloride"],
    "pp":         ["polypropylene"],
    "ac":         ["air conditioner","air conditioning"],
    "led":        ["light emitting diode"],
    "cctv":       ["surveillance camera"],
    "ups":        ["uninterruptible power supply"],
    "cnc":        ["computer numerical control"],
    "peb":        ["pre-engineered building"],
}

SEMANTIC_THRESHOLD = 0.7   # minimum score for semantic candidates


# ══════════════════════════════════════════════════════════════════════════════
# LOADERS
# ══════════════════════════════════════════════════════════════════════════════
def load_catalogue(path: str) -> dict[str, str]:
    """Returns {mcat_id: mcat_name}."""
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mid  = str(row.get("glcat_mcat_id","")).strip()
            name = str(row.get("glcat_mcat_name","")).strip()
            if mid and name:
                out[mid] = name
    return out


def load_tree(path: str) -> tuple[dict, dict]:
    """
    Returns:
      mcat_info      {mcat_id: {mcat_name, mcat_level, listing_count,
                                 primary_pmcat_id, all_pmcat_ids,
                                 pmcat_name, pmcat_level,
                                 cat_id, cat_name, group_id, group_name,
                                 is_orphan}}
      pmcat_children {pmcat_id: [{mcat_id, mcat_name, listing_count}]}
    """
    all_rows: dict[str, list] = defaultdict(list)
    pmcat_children: dict[str, list] = defaultdict(list)
    seen_in_pmcat: dict[str, set] = defaultdict(set)

    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mid  = str(row.get("MCAT ID","")).strip()
            pid  = str(row.get("PMCAT ID","")).strip()
            name = str(row.get("MCAT Name","")).strip()
            lc   = str(row.get("Listing Count","")).strip()
            if not mid:
                continue
            all_rows[mid].append(row)
            if pid and pid not in ("","nan"):
                if mid not in seen_in_pmcat[pid]:
                    seen_in_pmcat[pid].add(mid)
                    pmcat_children[pid].append({
                        "mcat_id":       mid,
                        "mcat_name":     name,
                        "listing_count": lc or None,
                    })

    mcat_info: dict[str, dict] = {}
    for mid, rows in all_rows.items():
        valid = [r for r in rows
                 if str(r.get("PMCAT ID","")).strip() not in ("","nan")]
        if not valid:
            r = rows[0]
            mcat_info[mid] = {
                "mcat_name":        str(r.get("MCAT Name","")).strip(),
                "mcat_level":       str(r.get("MCAT Level","")).strip() or None,
                "listing_count":    str(r.get("Listing Count","")).strip() or None,
                "primary_pmcat_id": None,
                "all_pmcat_ids":    [],
                "pmcat_name":       None,
                "pmcat_level":      None,
                "cat_id":           str(r.get("CAT ID","")).strip() or None,
                "cat_name":         str(r.get("CAT Name","")).strip() or None,
                "group_id":         str(r.get("Group ID","")).strip() or None,
                "group_name":       str(r.get("Group Name","")).strip() or None,
                "is_orphan":        True,
            }
            continue

        def sort_key(r):
            try: lvl = int(float(str(r.get("PMCAT Level","99"))))
            except: lvl = 99
            is_self = str(r.get("PMCAT ID","")) == mid
            return (lvl, 1 if is_self else 0)

        valid.sort(key=sort_key)
        primary = valid[0]
        all_pmcat_ids = list(dict.fromkeys(
            str(r.get("PMCAT ID","")).strip()
            for r in valid
            if str(r.get("PMCAT ID","")).strip() not in ("","nan")
        ))
        mcat_info[mid] = {
            "mcat_name":        str(primary.get("MCAT Name","")).strip(),
            "mcat_level":       str(primary.get("MCAT Level","")).strip() or None,
            "listing_count":    str(primary.get("Listing Count","")).strip() or None,
            "primary_pmcat_id": str(primary.get("PMCAT ID","")).strip(),
            "all_pmcat_ids":    all_pmcat_ids,
            "pmcat_name":       str(primary.get("PMCAT Name","")).strip() or None,
            "pmcat_level":      str(primary.get("PMCAT Level","")).strip() or None,
            "cat_id":           str(primary.get("CAT ID","")).strip() or None,
            "cat_name":         str(primary.get("CAT Name","")).strip() or None,
            "group_id":         str(primary.get("Group ID","")).strip() or None,
            "group_name":       str(primary.get("Group Name","")).strip() or None,
            "is_orphan":        False,
        }

    return mcat_info, pmcat_children


def load_overlap(path: str) -> tuple[dict, list]:
    """
    Returns:
      overlap_by_name  {mcat_name_lower: [overlap_row, ...]}
                       Each row has both MCATss' names + metrics
      all_pairs        list of all raw rows (for family context)
    """
    overlap_by_name: dict[str, list] = defaultdict(list)
    all_pairs = []

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            all_pairs.append(dict(row))
            m1 = str(row.get("MCAT_1","")).strip()
            m2 = str(row.get("MCAT_2","")).strip()
            if m1: overlap_by_name[m1.lower()].append(dict(row))
            if m2: overlap_by_name[m2.lower()].append(dict(row))

    return overlap_by_name, all_pairs


def load_platform(path: str) -> dict[str, list]:
    """
    Returns {root_mcat_name_lower: [related_mcat_name, ...]}
    """
    platform: dict[str, list] = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            root = str(row.get("glcat_mcat_name","")).strip().lower()
            rel  = str(row.get("related_mcat_name","")).strip()
            if root and rel:
                platform[root].append(rel)
    return platform


# ══════════════════════════════════════════════════════════════════════════════
# TOKENISATION + SCORING
# ══════════════════════════════════════════════════════════════════════════════
def tokenise(name: str) -> list[str]:
    tokens = re.split(r"[\s\-/,&]+", name.lower())
    return [t for t in tokens if t and t not in STOP_WORDS and len(t) > 1]


def score_semantic(root_tokens: list[str], root_name: str,
                   cand_name: str) -> tuple[float, str, bool]:
    """Returns (score, pre_note, synonym_matched)."""
    cand_token_set = set(tokenise(cand_name))
    cand_lower = cand_name.lower()

    # Keyword overlap — full token match only
    matched = [t for t in root_tokens if t in cand_token_set]
    n_root, n_match = len(root_tokens), len(matched)

    if cand_lower == root_name.lower():
        kw_score = 1.0
    elif n_match == n_root:
        kw_score = 0.9
    elif n_match > n_root / 2:
        kw_score = 0.7
    elif n_match == 1:
        kw_score = 0.4
    else:
        return 0.0, "", False

    fz = fuzzy_score(root_name, cand_name)
    score = kw_score + 0.3 * fz

    synonym_matched = False
    syn_found = []
    for tok in root_tokens:
        for syn in SYNONYM_MAP.get(tok, []):
            words = syn.split()
            hit = (syn in cand_token_set) if len(words)==1 else (syn in cand_lower)
            if hit:
                score += 0.2
                synonym_matched = True
                syn_found.append(f"{tok}→{syn}")
                break

    parts = []
    if matched:    parts.append(f"Token match: {', '.join(matched)}")
    if syn_found:  parts.append(f"Synonym match: {', '.join(syn_found)}")
    note = "; ".join(parts) or "Score-based match"

    return round(min(score, 1.0), 4), note, synonym_matched


def pre_label(root_name: str, cand_name: str,
              score: float, synonym_matched: bool) -> tuple[str, str]:
    relevance = "high" if (score >= 0.7 or synonym_matched) else \
                "medium" if score >= 0.4 else "low"
    root_l, cand_l = root_name.lower(), cand_name.lower()
    if root_l in cand_l:
        relationship = "likely_parent"
    elif cand_l in root_l:
        relationship = "likely_child"
    else:
        primary_tok = tokenise(root_name)[0] if tokenise(root_name) else ""
        relationship = "likely_sibling" if primary_tok and primary_tok in set(tokenise(cand_name)) \
                        else "unknown"
    return relevance, relationship


# ══════════════════════════════════════════════════════════════════════════════
# TAXONOMY CONTEXT + SIBLING RESOLUTION
# ══════════════════════════════════════════════════════════════════════════════
def grandparent_pmcat(pmcat_id: str, mcat_info: dict) -> str | None:
    """
    Returns the grandparent PMCAT ID for a given PMCAT,
    i.e. the parent of that PMCAT which must itself be a PMCAT (not a CAT).
    Returns None when the immediate PMCAT's parent is a CAT.
    """
    info = mcat_info.get(str(pmcat_id))
    if not info:
        return None
    pp_id = info.get("primary_pmcat_id")
    if not pp_id or pp_id == str(pmcat_id):   # self-ref = no real parent PMCAT
        return None
    return pp_id


def build_taxonomy_context(mcat_id: str, mcat_info: dict,
                            pmcat_children: dict) -> dict:
    info = mcat_info.get(str(mcat_id))
    if not info:
        return {"mcat_id": mcat_id, "error": "not_found_in_tree"}

    # Full path
    parts = []
    if info.get("group_name"): parts.append(info["group_name"])
    if info.get("cat_name"):   parts.append(info["cat_name"])
    if info.get("pmcat_name") and info["pmcat_name"] != info["mcat_name"]:
        parts.append(info["pmcat_name"])
    parts.append(info["mcat_name"])

    # Direct siblings (Tier 1a) — all MCATss sharing any PMCAT with root
    direct_sibling_ids: set[str] = set()
    direct_siblings: list[dict] = []
    for pid in info.get("all_pmcat_ids", []):
        for sib in pmcat_children.get(pid, []):
            sid = sib["mcat_id"]
            if sid == mcat_id or sid in direct_sibling_ids:
                continue
            direct_sibling_ids.add(sid)
            direct_siblings.append({
                **sib,
                "source_pmcat":    pid,
                "sibling_type":    "direct",
            })

    # Indirect siblings (Tier 1b) — grandparent PMCAT's other children
    # Only when primary PMCAT's parent is ALSO a PMCAT (not a CAT)
    primary_pmcat_id = info.get("primary_pmcat_id")
    gp_id = grandparent_pmcat(primary_pmcat_id, mcat_info) if primary_pmcat_id else None

    indirect_siblings: list[dict] = []
    if gp_id:
        for sib in pmcat_children.get(gp_id, []):
            sid = sib["mcat_id"]
            if sid == mcat_id or sid in direct_sibling_ids:
                continue
            indirect_siblings.append({
                **sib,
                "source_pmcat":    gp_id,
                "sibling_type":    "indirect",
            })

    all_siblings = direct_siblings + indirect_siblings

    return {
        "mcat_id":        mcat_id,
        "mcat_name":      info["mcat_name"],
        "mcat_level":     info.get("mcat_level"),
        "listing_count":  info.get("listing_count"),
        "full_path":      " > ".join(parts),
        "is_orphan":      info.get("is_orphan", False),
        "group":   {"id": info.get("group_id"),  "name": info.get("group_name")}  if info.get("group_id")  else None,
        "subcat":  {"id": info.get("cat_id"),    "name": info.get("cat_name")}    if info.get("cat_id")    else None,
        "parent":  {"id": primary_pmcat_id,      "name": info.get("pmcat_name"),
                    "level": info.get("pmcat_level")}                              if primary_pmcat_id else None,
        "grandparent_pmcat_id": gp_id,
        "all_pmcat_ids":  info.get("all_pmcat_ids", []),
        "siblings":       all_siblings,
        "direct_sibling_count":   len(direct_siblings),
        "indirect_sibling_count": len(indirect_siblings),
    }


# ══════════════════════════════════════════════════════════════════════════════
# OVERLAP UTILITIES
# ══════════════════════════════════════════════════════════════════════════════
def extract_overlap_data(root_name: str, other_name: str,
                          row: dict) -> dict:
    """Pull the overlap metrics for 'other_name' relative to 'root_name'."""
    m1 = str(row.get("MCAT_1","")).strip()
    m2 = str(row.get("MCAT_2","")).strip()

    def safe_float(v):
        try: return float(str(v).replace("%","").strip())
        except: return None

    def safe_int(v):
        try: return int(float(str(v).strip()))
        except: return None

    if m1.lower() == root_name.lower():
        return {
            "total_products":               safe_int(row.get("MCAT_2_Products")),
            "total_suppliers":              safe_int(row.get("MCAT_2_Supplier")),
            "common_products":              safe_int(row.get("Common_Product")),
            "common_suppliers":             safe_int(row.get("Common_Suppliers")),
            "product_overlap_pct_root":     safe_float(row.get("product_overlap_pct (M1.M2)/M1")),
            "product_overlap_pct_candidate": safe_float(row.get("product_overlap_pct (M1.M2)/M2")),
            "supplier_overlap_pct_root":    safe_float(row.get("supplier_overlap_pct (M1.M2)/M1")),
            "supplier_overlap_pct_candidate": safe_float(row.get("supplier_overlap_pct (M1.M2)/M2")),
        }
    else:
        return {
            "total_products":               safe_int(row.get("MCAT_1_Products")),
            "total_suppliers":              safe_int(row.get("MCAT_1_Supplier")),
            "common_products":              safe_int(row.get("Common_Product")),
            "common_suppliers":             safe_int(row.get("Common_Suppliers")),
            "product_overlap_pct_root":     safe_float(row.get("product_overlap_pct (M1.M2)/M2")),
            "product_overlap_pct_candidate": safe_float(row.get("product_overlap_pct (M1.M2)/M1")),
            "supplier_overlap_pct_root":    safe_float(row.get("supplier_overlap_pct (M1.M2)/M2")),
            "supplier_overlap_pct_candidate": safe_float(row.get("supplier_overlap_pct (M1.M2)/M1")),
        }


# ══════════════════════════════════════════════════════════════════════════════
# FAMILY CONTEXT PAIRS (Source C)
# ══════════════════════════════════════════════════════════════════════════════
def build_family_context_pairs(sibling_names: set[str],
                                all_pairs: list[dict]) -> list[dict]:
    """
    Returns all overlap pairs where BOTH MCATss are in the sibling set.
    Does NOT add new candidates. Used by Agent 4 for per-candidate notes.
    """
    result = []
    sib_lower = {n.lower() for n in sibling_names}
    for row in all_pairs:
        m1 = str(row.get("MCAT_1","")).strip()
        m2 = str(row.get("MCAT_2","")).strip()
        if m1.lower() in sib_lower and m2.lower() in sib_lower:
            def sf(v):
                try: return float(str(v).replace("%","").strip())
                except: return None
            def si(v):
                try: return int(float(str(v).strip()))
                except: return None
            result.append({
                "mcat_a": m1,
                "mcat_b": m2,
                "common_products":       si(row.get("Common_Product")),
                "common_suppliers":      si(row.get("Common_Suppliers")),
                "product_overlap_pct_a": sf(row.get("product_overlap_pct (M1.M2)/M1")),
                "product_overlap_pct_b": sf(row.get("product_overlap_pct (M1.M2)/M2")),
                "supplier_overlap_pct_a": sf(row.get("supplier_overlap_pct (M1.M2)/M1")),
                "supplier_overlap_pct_b": sf(row.get("supplier_overlap_pct (M1.M2)/M2")),
            })
    return result


# ══════════════════════════════════════════════════════════════════════════════
# CANDIDATE POOL BUILDER
# ══════════════════════════════════════════════════════════════════════════════
def build_candidate_pool(
    root_mcat_id:   str,
    root_mcat_name: str,
    taxonomy_ctx:   dict,
    catalogue:      dict,
    overlap_by_name: dict,
    all_pairs:      list,
    platform_links: dict,
    mcat_info:      dict,
) -> tuple[list[dict], list[dict]]:
    """
    Returns (candidates, family_context_pairs).
    candidates: deduplicated list, each with source_flags and overlap_data.
    """
    pool: dict[str, dict] = {}       # mcat_id → candidate entry
    root_name_lower = root_mcat_name.lower()

    # Reverse name→id lookup for Tier 2/3 name-based candidates
    name_to_id: dict[str, str] = {v.lower(): k for k, v in catalogue.items()}

    def resolve_id(mcat_id: str, mcat_name: str) -> str:
        """Resolve name:-prefixed keys to real IDs where possible."""
        if not str(mcat_id).startswith("name:"):
            return str(mcat_id)
        return name_to_id.get(mcat_name.lower(), mcat_id)

    def get_tree_data(mcat_id: str):
        """Returns (mcat_level, listing_count) from mcat_info. Both None if not found."""
        info = mcat_info.get(str(mcat_id))
        if not info:
            return None, None
        return info.get("mcat_level"), info.get("listing_count")

    def upsert(mcat_id: str, mcat_name: str, tier: str,
               pre_relevance: str, pre_relationship: str,
               similarity_score, pre_note: str,
               overlap_data=None):
        mcat_id = resolve_id(str(mcat_id), mcat_name)
        if mcat_id == str(root_mcat_id):
            return
        if mcat_id not in pool:
            # Look up tree data for every candidate regardless of tier
            mcat_level, listing_count = get_tree_data(mcat_id)
            pool[mcat_id] = {
                "mcat_id":             mcat_id,
                "mcat_name":           mcat_name,
                "mcat_level":          mcat_level,     # from tree, None if MCAT not in tree
                "listing_count":       listing_count,  # from tree, None if not found
                "source_flags":        [],
                "source_tier_primary": tier,
                "pre_relevance":       pre_relevance,
                "pre_relationship":    pre_relationship,
                "similarity_score":    similarity_score,
                "pre_note":            pre_note,
                "overlap_data":        None,
            }
        entry = pool[mcat_id]
        if tier not in entry["source_flags"]:
            entry["source_flags"].append(tier)
        # Attach overlap data if provided and not already set
        if overlap_data and entry["overlap_data"] is None:
            entry["overlap_data"] = overlap_data

    # ── Tier 1a — direct siblings ──────────────────────────────────────────
    for sib in taxonomy_ctx.get("siblings", []):
        if sib.get("sibling_type") == "direct":
            upsert(sib["mcat_id"], sib["mcat_name"],
                   "structural_direct", "high", "likely_sibling",
                   1.0, f"Direct sibling — PMCAT {sib['source_pmcat']}")

    # ── Tier 1b — indirect siblings ────────────────────────────────────────
    for sib in taxonomy_ctx.get("siblings", []):
        if sib.get("sibling_type") == "indirect":
            upsert(sib["mcat_id"], sib["mcat_name"],
                   "structural_indirect", "high", "likely_sibling",
                   1.0, f"Indirect sibling — grandparent PMCAT {sib['source_pmcat']}")

    # ── Tier 2 — overlap CSV (all root pairs) ──────────────────────────────
    for row in overlap_by_name.get(root_name_lower, []):
        m1 = str(row.get("MCAT_1","")).strip()
        m2 = str(row.get("MCAT_2","")).strip()
        other_name = m2 if m1.lower() == root_name_lower else m1
        if not other_name or other_name.lower() == root_name_lower:
            continue
        # Find mcat_id for other_name from catalogue (reverse lookup)
        other_id = next((k for k, v in catalogue.items()
                         if v.lower() == other_name.lower()), None)
        if not other_id:
            # Use name as key if ID not found
            other_id = f"name:{other_name.lower()}"
        ov = extract_overlap_data(root_mcat_name, other_name, row)
        upsert(other_id, other_name,
               "overlap", "high", "unknown",
               None, "Overlap-confirmed — root pair",
               overlap_data=ov)

    # ── Tier 3 — platform links (all for this root) ────────────────────────
    for rel_name in platform_links.get(root_name_lower, []):
        if not rel_name or rel_name.lower() == root_name_lower:
            continue
        rel_id = next((k for k, v in catalogue.items()
                       if v.lower() == rel_name.lower()), f"name:{rel_name.lower()}")
        upsert(rel_id, rel_name,
               "platform", "high", "unknown",
               None, "Platform related-category link — audit required")

    # ── Tier 4 — semantic (all score >= 0.7, no cap) ───────────────────────
    root_tokens = tokenise(root_mcat_name)
    for cand_id, cand_name in catalogue.items():
        if cand_id == str(root_mcat_id):
            continue
        if cand_id in pool:
            continue  # already captured by structural/overlap/platform
        score, note, syn = score_semantic(root_tokens, root_mcat_name, cand_name)
        if score >= SEMANTIC_THRESHOLD:
            rel, rel_type = pre_label(root_mcat_name, cand_name, score, syn)
            upsert(cand_id, cand_name,
                   "semantic", rel, rel_type, score, note)

    candidates = list(pool.values())

    # ── Family context pairs (Source C) ────────────────────────────────────
    sibling_names = {c["mcat_name"] for c in candidates
                     if any(t in c["source_flags"]
                            for t in ("structural_direct","structural_indirect"))}
    sibling_names.add(root_mcat_name)
    fcp = build_family_context_pairs(sibling_names, all_pairs)

    return candidates, fcp


# ══════════════════════════════════════════════════════════════════════════════
# MAIN PER-MCAT FUNCTION
# ══════════════════════════════════════════════════════════════════════════════
def run(root_mcat_id: str, root_mcat_name: str,
        catalogue: dict, mcat_info: dict, pmcat_children: dict,
        overlap_by_name: dict, all_pairs: list,
        platform_links: dict, output_dir: str) -> None:

    out_path = Path(output_dir) / str(root_mcat_id)
    out_path.mkdir(parents=True, exist_ok=True)

    # Build taxonomy context (tree-derived)
    ctx = build_taxonomy_context(root_mcat_id, mcat_info, pmcat_children)

    # Build full candidate pool
    candidates, fcp = build_candidate_pool(
        root_mcat_id, root_mcat_name, ctx,
        catalogue, overlap_by_name, all_pairs,
        platform_links, mcat_info,
    )

    # Candidate summary
    tier_counts: dict[str, int] = {}
    for c in candidates:
        for sf in c["source_flags"]:
            tier_counts[sf] = tier_counts.get(sf, 0) + 1
    multi_source = sum(1 for c in candidates if len(c["source_flags"]) > 1)

    # Assemble agent4_input.json
    output = {
        "root_mcat_id":   root_mcat_id,
        "root_mcat_name": root_mcat_name,
        "taxonomy_context": ctx,
        "candidate_summary": {
            "total":        len(candidates),
            "multi_source": multi_source,
            **{k: v for k, v in tier_counts.items()},
        },
        "candidates":           candidates,
        "family_context_pairs": fcp,
    }

    out_file = out_path / "agent4_input.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(
        f"[{root_mcat_id}] {root_mcat_name} | "
        f"total={len(candidates)} "
        f"(direct={tier_counts.get('structural_direct',0)} "
        f"indirect={tier_counts.get('structural_indirect',0)} "
        f"overlap={tier_counts.get('overlap',0)} "
        f"platform={tier_counts.get('platform',0)} "
        f"semantic={tier_counts.get('semantic',0)}) "
        f"| family_pairs={len(fcp)}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR INTERFACE
# ══════════════════════════════════════════════════════════════════════════════
_catalogue:       dict | None = None
_mcat_info:       dict | None = None
_pmcat_children:  dict | None = None
_overlap_by_name: dict | None = None
_all_pairs:       list | None = None
_platform_links:  dict | None = None


def startup(all_mcats_path: str, tree_path: str,
            overlap_path: str | None = None,
            platform_path: str | None = None) -> None:
    global _catalogue, _mcat_info, _pmcat_children
    global _overlap_by_name, _all_pairs, _platform_links

    print("Preprocessor startup...")
    _catalogue = load_catalogue(all_mcats_path)
    _mcat_info, _pmcat_children = load_tree(tree_path)

    if overlap_path and os.path.exists(overlap_path):
        _overlap_by_name, _all_pairs = load_overlap(overlap_path)
        print(f"  Overlap CSV: {sum(len(v) for v in _overlap_by_name.values()):,} indexed entries")
    else:
        _overlap_by_name, _all_pairs = {}, []
        if overlap_path:
            print(f"  Overlap CSV not found at {overlap_path} — Tier 2 skipped")

    if platform_path and os.path.exists(platform_path):
        _platform_links = load_platform(platform_path)
        print(f"  Platform links: {sum(len(v) for v in _platform_links.values()):,} links across {len(_platform_links):,} MCATss")
    else:
        _platform_links = {}
        if platform_path:
            print(f"  Platform CSV not found at {platform_path} — Tier 3 skipped")

    print(
        f"  Catalogue: {len(_catalogue):,} | "
        f"Tree MCATss: {len(_mcat_info):,} | "
        f"PMCAT families: {len(_pmcat_children):,}"
    )


def preprocess(mcat_id: str, mcat_name: str, output_dir: str) -> None:
    if _catalogue is None:
        raise RuntimeError("Call startup() before preprocess()")
    run(str(mcat_id), mcat_name,
        _catalogue, _mcat_info, _pmcat_children,
        _overlap_by_name, _all_pairs, _platform_links,
        output_dir)


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCAT preprocessor v3.0")
    parser.add_argument("--mcat_id",    required=True)
    parser.add_argument("--mcat_name",  required=True)
    parser.add_argument("--all_mcats",  required=True)
    parser.add_argument("--tree",       required=True)
    parser.add_argument("--overlap",    default=None)
    parser.add_argument("--platform",   default=None)
    parser.add_argument("--output_dir", default="output")
    args = parser.parse_args()

    startup(args.all_mcats, args.tree, args.overlap, args.platform)
    preprocess(args.mcat_id, args.mcat_name, args.output_dir)
