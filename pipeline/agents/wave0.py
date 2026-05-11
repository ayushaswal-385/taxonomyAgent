"""Agents for Wave 0: Agent 1 (PDF Enricher) and Agent 2 (Product Verifier)."""
import base64
import io
import json
from PIL import Image, ImageOps


AGENT2_IMAGE_MAX_BYTES = int(4.8 * 1024 * 1024)


def _normalize_agent2_mime(b64: str, fallback: str = "image/jpeg") -> str:
    """Infer MIME from base64 signature to avoid upstream mismatches."""
    if b64.startswith("/9j/"):
        return "image/jpeg"
    if b64.startswith("iVBOR"):
        return "image/png"
    if b64.startswith("UklGR"):
        return "image/webp"
    if b64.startswith("R0lG"):
        return "image/gif"
    return fallback


def _compress_agent2_image_if_needed(item: dict) -> dict | None:
    """Shrink oversized images for Agent 2 so Anthropic accepts them."""
    b64 = item.get("image_base64")
    if not b64:
        return None

    mime = _normalize_agent2_mime(b64, item.get("image_mime_type", "image/jpeg"))

    try:
        raw = base64.b64decode(b64)
    except Exception as e:
        print(f"    ⚠ [Agent 2] Failed to decode image for item {item.get('item_id')}: {e}")
        return None

    if len(raw) <= AGENT2_IMAGE_MAX_BYTES:
        return {"base64": b64, "mime_type": mime}

    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            rgba = img.convert("RGBA")
            alpha = rgba.getchannel("A")
            background.paste(rgba, mask=alpha)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        best_bytes = None
        max_dims = [None, 2400, 2000, 1600, 1280, 1024, 768]
        qualities = [85, 75, 65, 55, 45, 35]

        for max_dim in max_dims:
            working = img.copy()
            if max_dim and max(working.size) > max_dim:
                working.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

            for quality in qualities:
                buf = io.BytesIO()
                working.save(buf, format="JPEG", quality=quality, optimize=True)
                candidate = buf.getvalue()
                if best_bytes is None or len(candidate) < len(best_bytes):
                    best_bytes = candidate
                if len(candidate) <= AGENT2_IMAGE_MAX_BYTES:
                    print(
                        f"    [Agent 2] Compressed oversized image for item {item.get('item_id')} "
                        f"from {len(raw):,} to {len(candidate):,} bytes."
                    )
                    return {
                        "base64": base64.b64encode(candidate).decode("utf-8"),
                        "mime_type": "image/jpeg",
                    }

        if best_bytes is not None:
            print(
                f"    ⚠ [Agent 2] Could not compress item {item.get('item_id')} below "
                f"{AGENT2_IMAGE_MAX_BYTES:,} bytes; best={len(best_bytes):,}. Skipping image."
            )
    except Exception as e:
        print(f"    ⚠ [Agent 2] Compression failed for item {item.get('item_id')}: {e}")

    return None

def run_agent_01(client, mcat_name, mcat_id, pdf_paths, work_dir):
    """Agent 1 — PDF Enricher. Returns pdf_summary dict."""
    if not pdf_paths:
        print("    → Agent 1: No PDFs provided, returning null")
        return {"pdf_summary": None}

    pdf_text = ""
    try:
        import pdfplumber
        import os
        import subprocess

        for i, path in enumerate(pdf_paths[:5]):
            target_path = path
            
            # Compress if PDF is over 50MB
            if os.path.getsize(path) > 50 * 1024 * 1024:
                print(f"    [Agent 1] PDF {os.path.basename(path)} is over 50MB. Compressing...")
                compressed_path = path + ".compressed.pdf"
                try:
                    # Use Ghostscript with /screen settings for max compression (suitable for text extraction)
                    subprocess.run([
                        "gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
                        "-dPDFSETTINGS=/screen", "-dNOPAUSE", "-dQUIET", "-dBATCH",
                        f"-sOutputFile={compressed_path}", path
                    ], check=True, capture_output=True)
                    
                    if os.path.exists(compressed_path):
                        target_path = compressed_path
                except Exception as comp_e:
                    print(f"    ⚠ PDF compression failed: {comp_e}. Proceeding with original file.")

            with pdfplumber.open(target_path) as pdf:
                for page in pdf.pages[:20]:
                    txt = page.extract_text() or ""
                    pdf_text += f"\n--- PDF {i+1} Page {page.page_number} ---\n{txt}"
                    
            # Cleanup temporary compressed file
            if target_path != path and os.path.exists(target_path):
                os.remove(target_path)
                
        pdf_text = pdf_text[:30000]
    except Exception as e:
        print(f"    ⚠ PDF extraction error: {e}")
        return {"pdf_summary": None}

    system = f"""You are Agent 1 — PDF Enricher for the MCAT Taxonomy Pipeline.
Role: Extract structured product data from seller PDF text for the target MCAT category.

Target Category: "{mcat_name}"

Categorize every product into:
1. "Identified for input category" — matches the target category
2. "Other categories" — does not match
3. "Unidentified" — insufficient info

For each product extract: Product Category, Product Name, Product Description, Product Specifications, Product Price, Product Units, Product Image descriptions.
If a field is not stated, use "Not available".

RESPOND WITH ONLY VALID JSON matching this schema:
{{
  "pdf_summary": {{
    "pdf_count_processed": <int>,
    "mcat_name": "{mcat_name}",
    "agent1_pdf_supplement": [
      {{"Product Category":"","Product Name":"","Product Description":"","Product Specifications":"","Product Price":"","Product Units":"","Product Image descriptions":""}}
    ],
    "full_merged_json": {{
      "Identified for input category": [],
      "Other categories": [],
      "Unidentified": []
    }}
  }}
}}"""

    user = f"Extract products from these seller PDFs for MCAT '{mcat_name}':\n\n{pdf_text[:25000]}"
    result = client.call("Agent_01_PDF", mcat_name, system, user)
    return result.get("content", {"pdf_summary": None})


def run_agent_02(client, mcat_name, mcat_id, enriched_products):
    """Agent 2 — Product & Image Verifier. Returns verified product lists."""
    if not enriched_products:
        print("    → Agent 2: No products provided, returning absent")
        return {
            "input_data_absent": True,
            "verified_good_products": [], "verified_bad_products": [],
            "conflicts_resolved": [], "image_pattern_summary": None,
            "verified_good_image_urls": [], "verified_bad_image_urls": []
        }

    # Prepare items without base64 for the text prompt
    items_for_prompt = []
    images_for_vision = []
    for item in enriched_products:
        items_for_prompt.append({
            "item_id": item["item_id"],
            "ai_label": item["ai_label"],
            "image_url": item["image_url"],
            "image_status": item["image_status"],
            "product_page_url": item["product_page_url"],
        })
        if item.get("image_base64") and item["image_status"] == "ok":
            prepared = _compress_agent2_image_if_needed(item)
            if prepared:
                images_for_vision.append(prepared)

    system = f"""You are Agent 2 — Product & Image Verifier for MCAT "{mcat_name}".
Role: Verify AI-deemed good and bad product classifications by inspecting images and product page info.

For each GOOD item: Does it show a correct product for this MCAT? If YES → verified_label: good. If NO → verified_label: bad with failure_reason.
For each BAD item: What specifically is wrong? Identify failure from: wrong_product|wrong_mcat|wrong_material|is_service|inflatable|accessory|construction_service|thin_image|other.
If actually correct → override to good.

RESPOND WITH ONLY VALID JSON:
{{
  "input_data_absent": false,
  "verified_good_products": [
    {{"item_id":"","image_url":"","image_status":"","product_page_url":"","ai_label":"","verified_label":"good|bad|inconclusive","override":false,"verification_note":""}}
  ],
  "verified_bad_products": [
    {{"item_id":"","image_url":"","image_status":"","product_page_url":"","ai_label":"","verified_label":"","override":false,"failure_reason":"","correct_mcat_suggestion":null,"verification_note":""}}
  ],
  "conflicts_resolved": [],
  "image_pattern_summary": "2-3 sentence description",
  "verified_good_image_urls": [],
  "verified_bad_image_urls": []
}}"""

    user = f"MCAT: {mcat_name} (ID: {mcat_id})\n\nProducts to verify:\n{json.dumps(items_for_prompt, indent=2)}\n\nI have attached the product images. Verify each product's image against the MCAT category and assess correctness."

    result = client.call("Agent_02_Verifier", mcat_name, system, user,
                        images=images_for_vision[:5])
    content = result.get("content", {})
    if isinstance(content, str):
        content = {
            "input_data_absent": True,
            "verified_good_products": [], "verified_bad_products": [],
            "conflicts_resolved": [], "image_pattern_summary": None,
            "verified_good_image_urls": [], "verified_bad_image_urls": []
        }
    return content
