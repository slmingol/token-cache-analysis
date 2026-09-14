"""
Claude Code Cache Efficiency by Project — split ~/dev/projects vs ~/dev/bandwidth
5m cache = wasteful (expires fast, likely not reused)
1h cache = efficient (longer TTL, better reuse)
"""

import json
from collections import defaultdict
from pathlib import Path

GROUPS = {
    "dev/projects": "-Users-smingolelli-dev-projects-",
    "dev/bandwidth": "-Users-smingolelli-dev-bandwidth-",
}


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

    if m5 == 0 and h1 == 0:
        legacy = int(usage.get("cache_creation_input_tokens") or 0)
        if legacy > 0:
            m5 = legacy

    return m5, h1


def print_group(label, projects):
    if not projects:
        print(f"\n[{label}] — no cache data\n")
        return

    sorted_projects = sorted(projects.items(), key=lambda x: x[1]["5m"] + x[1]["1h"], reverse=True)

    print(f"\n{'='*105}")
    print(f"  {label}")
    print(f"{'='*105}")
    print(f"{'Project':<42} {'5m':>12} {'1h':>12} {'Total':>12} {'5m%':>7}  Verdict")
    print("-" * 105)

    efficient = wasteful = mixed = 0

    for proj, d in sorted_projects:
        total = d["5m"] + d["1h"]
        pct_5m = (d["5m"] / total * 100) if total > 0 else 0
        if pct_5m >= 70:
            verdict, flag = "WASTEFUL", "  <-- BAD"
            wasteful += 1
        elif pct_5m >= 30:
            verdict, flag = "MIXED", ""
            mixed += 1
        else:
            verdict, flag = "EFFICIENT", ""
            efficient += 1

        print(f"{proj[:41]:<42} {d['5m']:12,} {d['1h']:12,} {total:12,} {pct_5m:6.1f}%  {verdict}{flag}")

    g5m = sum(d["5m"] for d in projects.values())
    g1h = sum(d["1h"] for d in projects.values())
    gt = g5m + g1h
    gpct = (g5m / gt * 100) if gt > 0 else 0
    print("-" * 105)
    print(f"{'SUBTOTAL':<42} {g5m:12,} {g1h:12,} {gt:12,} {gpct:6.1f}%")
    print(f"\n  Efficient: {efficient}  Mixed: {mixed}  Wasteful: {wasteful}  ({len(projects)} total)")


def main():
    projects_dir = Path.home() / ".claude" / "projects"

    # group_label -> {proj_name -> {5m, 1h}}
    groups = {label: defaultdict(lambda: {"5m": 0, "1h": 0}) for label in GROUPS}

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        dirname = project_dir.name

        matched_label = None
        proj_name = None
        for label, prefix in GROUPS.items():
            if dirname.startswith(prefix):
                matched_label = label
                proj_name = dirname[len(prefix):]
                break

        if not matched_label:
            continue

        for jsonl_file in project_dir.glob("*.jsonl"):
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
                        groups[matched_label][proj_name]["5m"] += m5
                        groups[matched_label][proj_name]["1h"] += h1
            except Exception:
                pass

    for label in GROUPS:
        filtered = {k: v for k, v in groups[label].items() if v["5m"] + v["1h"] > 0}
        print_group(label, filtered)

    print()


if __name__ == "__main__":
    main()
