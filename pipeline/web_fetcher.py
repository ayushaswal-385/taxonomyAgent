"""
Web page fetcher — fetches IndiaMART and other pages, extracts text.
"""
import re
import time
import requests
from bs4 import BeautifulSoup
from pipeline.config import WEB_FETCH_TIMEOUT, WEB_FETCH_DELAY, WEB_FETCH_MAX_CONTENT

_last_fetch_time = 0.0

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_page(url: str, max_chars: int = None) -> dict:
    """
    Fetch a web page and extract structured text content.
    Returns: {url, status, title, text, error}
    """
    global _last_fetch_time
    if max_chars is None:
        max_chars = WEB_FETCH_MAX_CONTENT

    # Rate limit
    elapsed = time.time() - _last_fetch_time
    if elapsed < WEB_FETCH_DELAY:
        time.sleep(WEB_FETCH_DELAY - elapsed)

    result = {"url": url, "status": None, "title": "", "text": "", "error": None}

    try:
        resp = requests.get(url, headers=HEADERS, timeout=WEB_FETCH_TIMEOUT,
                            allow_redirects=True)
        _last_fetch_time = time.time()
        result["status"] = resp.status_code

        if resp.status_code != 200:
            result["error"] = f"HTTP {resp.status_code}"
            return result

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract title
        title_tag = soup.find("title")
        result["title"] = title_tag.get_text(strip=True) if title_tag else ""

        # Remove script/style/nav/footer
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()

        # Extract text
        text = soup.get_text(separator="\n", strip=True)
        # Collapse multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)

        result["text"] = text[:max_chars]

    except requests.Timeout:
        result["error"] = "timeout"
    except requests.ConnectionError:
        result["error"] = "connection_error"
    except Exception as e:
        result["error"] = str(e)[:200]

    return result


def fetch_indiamart_mcat_page(url: str) -> dict:
    """Fetch an IndiaMART MCAT directory page and extract listing data."""
    page = fetch_page(url, max_chars=20000)
    if page["error"]:
        return page

    # Try to extract structured listing info from the page text
    page["listings_text"] = page["text"]
    return page


def fetch_product_page(url: str) -> dict:
    """Fetch an IndiaMART product detail page."""
    page = fetch_page(url, max_chars=12000)
    return page
