"""
Pipeline configuration — API settings, model, timeouts.
"""
import os

# ── LiteLLM / Claude settings ────────────────────────────────────────────
MODEL = "openai/anthropic/claude-sonnet-4-6"
LITELLM_API_BASE = "http://imllm.intermesh.net/v1"
LITELLM_API_KEY = "s"

# ── Retry / timeout ──────────────────────────────────────────────────────
MAX_RETRIES = 3
TIMEOUT = 1500        # seconds — generous for heavy agents
RETRY_DELAY = 5        # base delay for exponential backoff (seconds)

# ── Generation parameters ────────────────────────────────────────────────
TEMPERATURE = 0.15     # low for structured JSON output
MAX_TOKENS = 60000     # max output tokens per agent call

# ── Wave 2 parallel execution ────────────────────────────────────────────
MAX_PARALLEL_AGENTS = 4  # limit concurrent LLM calls to avoid rate limits

# ── Web fetching ─────────────────────────────────────────────────────────
WEB_FETCH_TIMEOUT = 20       # seconds per HTTP request
WEB_FETCH_DELAY = 1.0        # seconds between requests (rate limit)
WEB_FETCH_MAX_CONTENT = 45000  # max chars of page text to pass to LLM

# ── Paths ─────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(PROJECT_ROOT, "input")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
