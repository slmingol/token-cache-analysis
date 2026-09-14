"""
Claude Code Cache Analyzer - Daily 5m vs 1h with 5m Percentage
Scans all your sessions and shows daily totals + 5m % of cache writes.
Pure Python — no external packages.
"""

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def extract_cache_tokens(data):
    """Extract 5m and 1h cache creation tokens from common Claude Code JSONL structures."""
    usage = None

    # Common structures: direct .usage or .message.usage
    if isinstance(data, dict):
        if "usage" in data:
            usage = data["usage"]
        elif "message" in data and isinstance(data["message"], dict) and "usage" in data["message"]:
            usage = data["message"]["usage"]

    if not usage or not isinstance(usage, dict):
        return 0, 0

    cache_creation = usage.get("cache_creation") or {}

    m5 = int(cache_creation.get("ephemeral_5m_input_tokens") or 0)
    h1 = int(cache_creation.get("ephemeral_1h_input_tokens") or 0)

    # Fallback to legacy field (treat as 5m for older logs)
    if m5 == 0 and h1 == 0:
        legacy = int(usage.get("cache_creation_input_tokens") or 0)
        if legacy > 0:
            m5 = legacy

    return m5, h1


def main():
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        print("❌ Could not find ~/.claude/projects/")
        print("   Make sure you've used Claude Code before.")
        return

    daily = defaultdict(lambda: {"5m": 0, "1h": 0})
    total_files = 0
    processed_turns = 0

    print("Scanning all Claude Code session files...")

    for jsonl_file in projects_dir.rglob("*.jsonl"):
        total_files += 1
        try:
            with jsonl_file.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    m5, h1 = extract_cache_tokens(data)
                    if m5 == 0 and h1 == 0:
                        continue

                    processed_turns += 1

                    # Get date (prefer log timestamp, fallback to file date)
                    day = None
                    for key in ["timestamp", "created_at", "time"]:
                        ts = data.get(key)
                        if not ts and isinstance(data.get("message"), dict):
                            ts = data["message"].get(key)
                        if ts and isinstance(ts, str):
                            try:
                                if ts.endswith("Z"):
                                    ts = ts.replace("Z", "+00:00")
                                dt = datetime.fromisoformat(ts)
                                day = dt.date()
                                break
                            except Exception:
                                pass

                    if not day:
                        day = datetime.fromtimestamp(jsonl_file.stat().st_mtime).date()

                    day_str = str(day)
                    daily[day_str]["5m"] += m5
                    daily[day_str]["1h"] += h1

        except Exception:
            pass  # skip unreadable files quietly

    if not daily:
        print("\n❌ No cache write data found in any sessions.")
        print("   Try running this diagnostic command and share the output:")
        print("   find ~/.claude/projects -name '*.jsonl' -exec grep -l cache_creation {} + | head -5")
        return

    # Print results
    print(f"\n{'Date':<12} {'5m cache':>12} {'1h cache':>12} {'Total writes':>15} {'5m %':>8}")
    print("-" * 78)

    grand_5m = grand_1h = 0

    for day_str in sorted(daily.keys()):
        d = daily[day_str]
        total_day = d["5m"] + d["1h"]
        pct_5m = (d["5m"] / total_day * 100) if total_day > 0 else 0

        print(f"{day_str:<12} {d['5m']:12,} {d['1h']:12,} {total_day:15,} {pct_5m:7.1f}%")

        grand_5m += d["5m"]
        grand_1h += d["1h"]

    print("-" * 78)
    grand_total = grand_5m + grand_1h
    grand_pct = (grand_5m / grand_total * 100) if grand_total > 0 else 0
    print(f"{'TOTAL':<12} {grand_5m:12,} {grand_1h:12,} {grand_total:15,} {grand_pct:7.1f}%")

    print(f"\nScanned {total_files} session files • Processed {processed_turns:,} turns with cache writes")


if __name__ == "__main__":
    main()
