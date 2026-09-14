#!/usr/bin/env python3
"""
Claude Code Cache Efficiency by Project
Groups projects by workspace dir and rates each EFFICIENT / MIXED / WASTEFUL.
5m cache = wasteful (expires fast, likely not reused)
1h cache = efficient (longer TTL, better reuse)
Pure Python — no external packages.
"""

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path


def _load_dotenv():
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

_load_dotenv()


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


def path_to_claude_prefix(path: Path) -> str:
    """Convert an absolute path to the ~/.claude/projects directory prefix format."""
    return path.expanduser().resolve().as_posix().replace("/", "-")


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
    home = Path.home()
    env_groups = os.environ.get("CACHE_GROUPS", "")
    default_groups = (
        [str(Path(g).expanduser()) for g in env_groups.split(":") if g.strip()]
        if env_groups
        else [str(home / "dev" / "projects"), str(home / "dev" / "bandwidth")]
    )
    default_sessions = Path(os.environ.get("SESSIONS_DIR", "~/.claude/projects")).expanduser()

    parser = argparse.ArgumentParser(
        description="Analyze Claude Code prompt cache efficiency, grouped by workspace.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Cache tiers:
  5m  ephemeral  — short TTL, cheap, often expires before reuse  (wasteful if high %)
  1h  ephemeral  — long TTL, higher cost, survives most turns    (efficient)

Verdicts:
  EFFICIENT   <30%% 5m
  MIXED       30-70%% 5m
  WASTEFUL    >70%% 5m

Examples:
  python3 claude_cache_by_project.py
  python3 claude_cache_by_project.py --groups ~/work ~/personal
  python3 claude_cache_by_project.py --sessions-dir /path/to/.claude/projects
        """,
    )
    parser.add_argument(
        "--groups",
        nargs="+",
        default=default_groups,
        metavar="DIR",
        help=f"workspace dirs to split by (default from $CACHE_GROUPS or built-in: {' '.join(default_groups)})",
    )
    parser.add_argument(
        "--sessions-dir",
        type=Path,
        default=default_sessions,
        metavar="DIR",
        help=f"path to Claude Code projects dir (default: {default_sessions}, or $SESSIONS_DIR)",
    )
    args = parser.parse_args()

    projects_dir = args.sessions_dir
    if not projects_dir.exists():
        print(f"ERROR: {projects_dir} not found. Use --sessions-dir to specify the path.")
        raise SystemExit(1)

    # Build prefix -> label map from the group paths
    groups_map = {}
    for g in args.groups:
        p = Path(g).expanduser().resolve()
        prefix = p.as_posix().replace("/", "-")
        label = str(p).replace(str(home) + "/", "~/")
        groups_map[prefix] = label

    group_data = {label: defaultdict(lambda: {"5m": 0, "1h": 0}) for label in groups_map.values()}

    print("claude_cache_by_project.py  [--groups DIR ...]  [--sessions-dir DIR]  [--help]")

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        dirname = project_dir.name

        matched_label = None
        proj_name = None
        for prefix, label in groups_map.items():
            if dirname.startswith(prefix + "-") or dirname == prefix:
                matched_label = label
                proj_name = dirname[len(prefix):].lstrip("-") or dirname
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
                        group_data[matched_label][proj_name]["5m"] += m5
                        group_data[matched_label][proj_name]["1h"] += h1
            except Exception:
                pass

    for label in groups_map.values():
        filtered = {k: v for k, v in group_data[label].items() if v["5m"] + v["1h"] > 0}
        print_group(label, filtered)

    print()


if __name__ == "__main__":
    main()
