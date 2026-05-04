"""
Image Pre-loader — pure Python, zero LLM cost.
Unzips image archives, matches item_id to filenames, converts to base64.
"""
import os
import re
import base64
import zipfile
import tempfile
from typing import List, Dict, Optional
from pipeline.file_resolver import read_csv_safe


SUPPORTED_EXTENSIONS = {".jpeg", ".jpg", ".png", ".webp"}


def _find_image_in_dir(directory: str, item_id: str) -> Optional[str]:
    """Find an image file matching item_id in directory (case-insensitive)."""
    if not directory or not os.path.isdir(directory):
        return None
    for fname in os.listdir(directory):
        name_part, ext = os.path.splitext(fname)
        if ext.lower() in SUPPORTED_EXTENSIONS:
            # Match by item_id in filename
            if name_part.strip() == str(item_id).strip():
                return os.path.join(directory, fname)
            # Also try matching if filename contains the item_id
            if str(item_id).strip() in name_part:
                return os.path.join(directory, fname)
    return None


def _image_to_base64(image_path: str) -> tuple:
    """Convert image file to base64 string. Returns (base64_str, mime_type)."""
    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {".jpeg": "image/jpeg", ".jpg": "image/jpeg",
                ".png": "image/png", ".webp": "image/webp"}
    mime_type = mime_map.get(ext, "image/jpeg")

    with open(image_path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode("utf-8"), mime_type


def _unzip_images(zip_path: str, extract_to: str) -> str:
    """Unzip image archive to a temporary directory."""
    if not zip_path or not os.path.exists(zip_path):
        return ""
    os.makedirs(extract_to, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_to)
        return extract_to
    except Exception as e:
        print(f"  ⚠ Failed to unzip {zip_path}: {e}")
        return ""


def preload_images(
    good_products_csv: Optional[str],
    bad_products_csv: Optional[str],
    good_images_zip: Optional[str],
    bad_images_zip: Optional[str],
    mcat_id: str,
    work_dir: str,
) -> List[Dict]:
    """
    Pre-load images for Agent 2.
    Returns enriched_products list with base64 images.
    """
    enriched = []

    # Unzip image archives
    good_img_dir = _unzip_images(
        good_images_zip,
        os.path.join(work_dir, "good_images")
    ) if good_images_zip else ""

    bad_img_dir = _unzip_images(
        bad_images_zip,
        os.path.join(work_dir, "bad_images")
    ) if bad_images_zip else ""

    # Process good products
    good_rows = read_csv_safe(good_products_csv) if good_products_csv else []
    for row in good_rows:
        row_mcat_id = row.get("fk_glcat_mcat_id", "").strip()
        if row_mcat_id != str(mcat_id):
            continue

        item_id = row.get("fk_pc_item_id", "").strip()
        image_url = row.get("pc_item_img_original", "").strip()
        product_url = row.get("product_page_url", "").strip()

        # Find image in zip
        img_path = _find_image_in_dir(good_img_dir, item_id)
        if img_path:
            b64, mime = _image_to_base64(img_path)
            enriched.append({
                "item_id": item_id,
                "ai_label": "good",
                "image_url": image_url,
                "image_base64": b64,
                "image_mime_type": mime,
                "image_status": "ok",
                "product_page_url": product_url,
            })
        else:
            enriched.append({
                "item_id": item_id,
                "ai_label": "good",
                "image_url": image_url,
                "image_base64": None,
                "image_mime_type": None,
                "image_status": "missing_from_zip",
                "product_page_url": product_url,
            })

    # Process bad products
    bad_rows = read_csv_safe(bad_products_csv) if bad_products_csv else []
    for row in bad_rows:
        row_mcat_id = row.get("fk_glcat_mcat_id", "").strip()
        if row_mcat_id != str(mcat_id):
            continue

        item_id = row.get("fk_pc_item_id", "").strip()
        image_url = row.get("pc_item_img_original", "").strip()
        product_url = row.get("product_page_url", "").strip()

        img_path = _find_image_in_dir(bad_img_dir, item_id)
        if img_path:
            b64, mime = _image_to_base64(img_path)
            enriched.append({
                "item_id": item_id,
                "ai_label": "bad",
                "image_url": image_url,
                "image_base64": b64,
                "image_mime_type": mime,
                "image_status": "ok",
                "product_page_url": product_url,
            })
        else:
            enriched.append({
                "item_id": item_id,
                "ai_label": "bad",
                "image_url": image_url,
                "image_base64": None,
                "image_mime_type": None,
                "image_status": "missing_from_zip",
                "product_page_url": product_url,
            })

    return enriched
