"""
Fuzzy filename resolver — handles variations in zip file contents.
"""
import os
import re
import zipfile
import tempfile
import shutil
import csv
from typing import Optional, Dict, List


# ── Pattern groups for fuzzy matching ─────────────────────────────────────
FILE_PATTERNS = {
    "mcat_list": [r"mcat_list\.csv"],
    "all_mcats": [r"all_mcats[_\-]?indiamart\.csv", r"all_mcats\.csv"],
    "google_keywords": [r"google[_\-]?search[_\-]?keywords\.csv", r"google[_\-]?keywords\.csv"],
    "internal_keywords": [r"internal[_\-]?search[_\-]?keywords\.csv", r"internal[_\-]?keywords\.csv"],
    "mcat_related": [r"mcat[_\-]?related[_\-]?categories\.csv", r"related[_\-]?categories\.csv"],
    "overlap": [r"related[_\-]?mcats[_\-]?overlap\.csv", r"overlap\.csv"],
    "good_products": [r"good[_\-]?products\.csv"],
    "bad_products": [r"bad[_\-]?products\.csv"],
    "good_images": [r"good[_\-]?(product[_\-]?)?images\.zip"],
    "bad_images": [r"bad[_\-]?(product[_\-]?)?images\.zip"],
    "call_insights": [r"pns[_\-]?call[_\-]?insights[_\-]?clean\.csv",
                      r"call[_\-]?insights\.csv", r"seller[_\-]?buyer[_\-]?call\.csv"],
    "thumbnail": [r"thumbnail\.(jpg|jpeg|png|webp)"],
}


def _match_file(filename: str, patterns: list) -> bool:
    basename = os.path.basename(filename).lower()
    return any(re.fullmatch(p, basename, re.IGNORECASE) for p in patterns)


def resolve_files(extract_dir: str) -> Dict[str, Optional[str]]:
    """
    Scan extracted zip directory and resolve each logical file to its path.
    Returns dict mapping logical name -> absolute path (or None if missing).
    """
    all_files = []
    for root, dirs, files in os.walk(extract_dir):
        for f in files:
            all_files.append(os.path.join(root, f))

    resolved = {}
    for logical_name, patterns in FILE_PATTERNS.items():
        matched = None
        for fpath in all_files:
            if _match_file(fpath, patterns):
                matched = fpath
                break
        resolved[logical_name] = matched

    # ── Find seller PDFs (any .pdf file) ──────────────────────────────────
    pdfs = [f for f in all_files
            if f.lower().endswith(".pdf") and os.path.basename(f) != "thumbnail.pdf"]
    resolved["seller_pdfs"] = pdfs if pdfs else []

    return resolved


def extract_zip(zip_path: str, dest_dir: str) -> str:
    """Extract a zip file to dest_dir, return the extraction directory."""
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)
    return dest_dir


def read_csv_safe(filepath: str) -> List[dict]:
    """Read CSV handling BOM and encoding issues."""
    if not filepath or not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception:
        with open(filepath, "r", encoding="latin-1") as f:
            reader = csv.DictReader(f)
            return list(reader)


def get_mcat_slug(mcat_name: str) -> str:
    """Convert MCAT name to filesystem-safe slug."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", mcat_name.strip()).strip("_").lower()
    return slug


def discover_input_zips(input_dir: str) -> List[str]:
    """Find all zip files in the input directory."""
    if not os.path.isdir(input_dir):
        return []
    return sorted([
        os.path.join(input_dir, f)
        for f in os.listdir(input_dir)
        if f.lower().endswith(".zip")
    ])
