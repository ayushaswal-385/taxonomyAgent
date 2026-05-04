"""
LLM Client — wraps litellm for Claude API calls with retry, JSON parsing, token tracking.
"""
import json
import re
import time
import traceback
import litellm
from pipeline.config import (
    MODEL, LITELLM_API_BASE, LITELLM_API_KEY,
    MAX_RETRIES, TIMEOUT, RETRY_DELAY, TEMPERATURE, MAX_TOKENS,
)
from pipeline.token_tracker import TokenTracker

# Suppress litellm debug logs
litellm.suppress_debug_info = True
litellm.set_verbose = False


class LLMClient:
    """Wrapper around litellm with retry, JSON enforcement, and token tracking."""

    def __init__(self, tracker: TokenTracker):
        self.tracker = tracker

    def call(self, agent_name: str, mcat_name: str,
             system_prompt: str, user_message: str,
             expect_json: bool = True,
             max_tokens: int = None,
             images: list = None) -> dict:
        """
        Make an LLM call with retry logic and token tracking.

        Args:
            agent_name: Name for tracking (e.g. "Agent_03_Context")
            mcat_name: MCAT being processed
            system_prompt: System message content
            user_message: User message content (text)
            expect_json: If True, parse response as JSON with retry
            max_tokens: Override default max tokens
            images: Optional list of {"base64": ..., "mime_type": ...} for vision

        Returns:
            {"content": str_or_dict, "raw": str, "input_tokens": int, "output_tokens": int}
        """
        if max_tokens is None:
            max_tokens = MAX_TOKENS

        messages = [{"role": "system", "content": system_prompt}]

        # Build user message (potentially multimodal)
        if images:
            content_parts = [{"type": "text", "text": user_message}]
            for img in images[:5]:  # Cap at 5 images to manage tokens
                if img.get("base64"):
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{img.get('mime_type', 'image/jpeg')};base64,{img['base64']}"
                        }
                    })
            messages.append({"role": "user", "content": content_parts})
        else:
            messages.append({"role": "user", "content": user_message})

        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self.tracker.start_timer(f"{agent_name}_{mcat_name}")

                response = litellm.completion(
                    model=MODEL,
                    messages=messages,
                    temperature=TEMPERATURE,
                    max_tokens=max_tokens,
                    timeout=TIMEOUT,
                    api_base=LITELLM_API_BASE,
                    api_key=LITELLM_API_KEY,
                )

                elapsed = self.tracker.stop_timer(f"{agent_name}_{mcat_name}")

                # Extract usage
                usage = response.get("usage", {}) if isinstance(response, dict) else getattr(response, "usage", None)
                input_tokens = 0
                output_tokens = 0
                if usage:
                    if isinstance(usage, dict):
                        input_tokens = usage.get("prompt_tokens", 0)
                        output_tokens = usage.get("completion_tokens", 0)
                    else:
                        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
                        output_tokens = getattr(usage, "completion_tokens", 0) or 0

                self.tracker.record(agent_name, mcat_name, input_tokens, output_tokens, elapsed)

                # Extract text content
                raw_text = ""
                if isinstance(response, dict):
                    raw_text = response["choices"][0]["message"]["content"]
                else:
                    raw_text = response.choices[0].message.content

                result = {
                    "raw": raw_text,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                }

                if expect_json:
                    parsed = self._parse_json(raw_text)
                    if parsed is not None:
                        result["content"] = parsed
                    else:
                        # Retry with stricter JSON prompt
                        if attempt < MAX_RETRIES:
                            print(f"    ⚠ {agent_name} JSON parse failed, retry {attempt+1}/{MAX_RETRIES}")
                            messages.append({"role": "assistant", "content": raw_text})
                            messages.append({"role": "user", "content": (
                                "Your previous response was not valid JSON. "
                                "Please respond with ONLY a valid JSON object. "
                                "No markdown fences, no explanation, no text before or after. "
                                "Just the raw JSON object starting with { and ending with }."
                            )})
                            continue
                        result["content"] = raw_text  # fallback to raw
                        print(f"    ⚠ {agent_name} — JSON parse failed on all retries, using raw text")
                else:
                    result["content"] = raw_text

                print(f"    ✓ {agent_name} — {input_tokens:,} in / {output_tokens:,} out ({elapsed:.1f}s)")
                return result

            except Exception as e:
                elapsed = self.tracker.stop_timer(f"{agent_name}_{mcat_name}")
                last_error = e
                print(f"    ✗ {agent_name} attempt {attempt} failed: {str(e)[:120]}")
                if attempt < MAX_RETRIES:
                    wait = RETRY_DELAY * (2 ** (attempt - 1))
                    print(f"      Retrying in {wait}s...")
                    time.sleep(wait)

        # All retries exhausted
        print(f"    ✗✗ {agent_name} FAILED after {MAX_RETRIES} attempts: {last_error}")
        return {
            "content": {"error": str(last_error), "agent": agent_name},
            "raw": "",
            "input_tokens": 0,
            "output_tokens": 0,
        }

    def _parse_json(self, text: str):
        """Extract JSON from LLM response text."""
        if not text:
            return None
        text = text.strip()

        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code fence
        patterns = [
            r"```json\s*\n(.*?)\n\s*```",
            r"```\s*\n(.*?)\n\s*```",
            r"\{.*\}",
        ]
        for pattern in patterns[:2]:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue

        # Try finding the largest {...} block
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end > brace_start:
            try:
                return json.loads(text[brace_start:brace_end + 1])
            except json.JSONDecodeError:
                pass

        return None
