"""
Claude Code Cache Analyzer - Daily 5m vs 1h with 5m Percentage
Scans all your sessions and shows daily totals + 5m % of cache writes.
Pure Python — no external packages.
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def extract_cache_tokens(data):
    usage = None
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

    # Fallback: treat legacy field as 5m
    if m5 == 0 and h1 == 0:
        legacy = int(usage.get("cache_creation_input_tokens") or 0)
        if legacy > 0:
            m5 = legacy

    return m5, h1


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Claude Code prompt cache writes by day.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Cache tiers:
  5m  ephemeral  — short TTL, cheap, often expires before reuse (wasteful)
  1h  ephemeral  — long TTL, higher cost, survives most session turns (efficient)

Examples:
  python3 claude_cache.py
  python3 claude_cache.py --sessions-dir /path/to/.claude/projects
        """,
    )
    parser.add_argument(
        "--sessions-dir",
        type=Path,
        default=Path.home() / ".claude" / "projects",
        metavar="DIR",
        help="path to Claude Code projects dir (default: ~/.claude/projects)",
    )
    args = parser.parse_args()

    projects_dir = args.sessions_dir
    if not projects_dir.exists():
        print(f"ERROR: {projects_dir} not found. Use --sessions-dir to specify the path.")
        raise SystemExit(1)

    daily = defaultdict(lambda: {"5m": 0, "1h": 0})
    total_files = 0
    processed_turns = 0

    print(f"Scanning {projects_dir} ...")

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
            pass

    if not daily:
        print("\nNo cache write data found.")
        print("Diagnostic: find ~/.claude/projects -name '*.jsonl' -exec grep -l cache_creation {} + | head -5")
        return

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
