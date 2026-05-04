"""
Token usage tracker — per-agent, per-MCAT, and grand totals.
"""
import json
import time
from collections import defaultdict


class TokenTracker:
    """Tracks input/output tokens per agent and per MCAT."""

    def __init__(self):
        self._agent_totals = defaultdict(lambda: {
            "input_tokens": 0, "output_tokens": 0,
            "calls": 0, "total_time_sec": 0.0
        })
        self._mcat_agent = defaultdict(lambda: defaultdict(lambda: {
            "input_tokens": 0, "output_tokens": 0, "calls": 0
        }))
        self._start_times = {}

    # ── timing helpers ────────────────────────────────────────────────────
    def start_timer(self, key: str):
        self._start_times[key] = time.time()

    def stop_timer(self, key: str) -> float:
        elapsed = time.time() - self._start_times.pop(key, time.time())
        return round(elapsed, 2)

    # ── record usage ──────────────────────────────────────────────────────
    def record(self, agent_name: str, mcat_name: str,
               input_tokens: int, output_tokens: int, elapsed: float = 0):
        a = self._agent_totals[agent_name]
        a["input_tokens"] += input_tokens
        a["output_tokens"] += output_tokens
        a["calls"] += 1
        a["total_time_sec"] += elapsed

        m = self._mcat_agent[mcat_name][agent_name]
        m["input_tokens"] += input_tokens
        m["output_tokens"] += output_tokens
        m["calls"] += 1

    # ── summaries ─────────────────────────────────────────────────────────
    def get_grand_totals(self) -> dict:
        total_in = sum(a["input_tokens"] for a in self._agent_totals.values())
        total_out = sum(a["output_tokens"] for a in self._agent_totals.values())
        return {
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "total_tokens": total_in + total_out,
            "total_calls": sum(a["calls"] for a in self._agent_totals.values()),
        }

    def print_summary(self):
        totals = self.get_grand_totals()
        print("\n" + "=" * 70)
        print("TOKEN USAGE SUMMARY")
        print("=" * 70)
        print(f"  Total input tokens:  {totals['total_input_tokens']:>12,}")
        print(f"  Total output tokens: {totals['total_output_tokens']:>12,}")
        print(f"  Total tokens:        {totals['total_tokens']:>12,}")
        print(f"  Total LLM calls:     {totals['total_calls']:>12,}")
        print("-" * 70)
        for name, stats in sorted(self._agent_totals.items()):
            print(f"  {name:<30s}  in={stats['input_tokens']:>8,}  "
                  f"out={stats['output_tokens']:>8,}  "
                  f"calls={stats['calls']}  "
                  f"time={stats['total_time_sec']:.1f}s")
        print("=" * 70 + "\n")

    # ── persist ───────────────────────────────────────────────────────────
    def save_report(self, filepath: str) -> dict:
        report = {
            "grand_totals": self.get_grand_totals(),
            "per_agent": {k: dict(v) for k, v in self._agent_totals.items()},
            "per_mcat": {
                mcat: {ag: dict(st) for ag, st in agents.items()}
                for mcat, agents in self._mcat_agent.items()
            },
        }
        with open(filepath, "w") as f:
            json.dump(report, f, indent=2)
        return report
