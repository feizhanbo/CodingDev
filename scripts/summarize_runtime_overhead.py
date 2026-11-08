"""Validate and summarize complete paired samples without rewriting raw evidence."""

import argparse
import json
from pathlib import Path
from statistics import median


def summarize(records):
    pairs = {}
    for record in records:
        backend = record["backend"]
        if backend not in {"custom", "langgraph"}:
            raise ValueError("Unexpected backend")
        pair = pairs.setdefault(record["pair"], {})
        if backend in pair:
            raise ValueError("Duplicate sample in a pair")
        if record["elapsed_seconds"] <= 0 or record["artifact_bytes"] <= 0:
            raise ValueError("Invalid time or artifact size")
        pair[backend] = record
    if len(pairs) < 10 or any(set(pair) != {"custom", "langgraph"} for pair in pairs.values()):
        raise ValueError("At least ten complete pairs are required")
    rows = []
    for number, pair in sorted(pairs.items()):
        custom, graph = pair["custom"], pair["langgraph"]
        if custom["contract"] != graph["contract"] or custom["contract"]["status"] != "completed":
            raise ValueError(f"Contract mismatch or failure in pair {number}")
        rows.append({
            "pair": number,
            "custom_seconds": custom["elapsed_seconds"],
            "langgraph_seconds": graph["elapsed_seconds"],
            "extra_seconds": graph["elapsed_seconds"] - custom["elapsed_seconds"],
            "overhead_percent": 100 * (graph["elapsed_seconds"] / custom["elapsed_seconds"] - 1),
            "artifact_ratio": graph["artifact_bytes"] / custom["artifact_bytes"],
        })
    overheads = [row["overhead_percent"] for row in rows]
    return {
        "pairs": rows,
        "median_paired_overhead_percent": median(overheads),
        "min_paired_overhead_percent": min(overheads),
        "max_paired_overhead_percent": max(overheads),
        "median_extra_seconds": median(row["extra_seconds"] for row in rows),
        "median_artifact_ratio": median(row["artifact_ratio"] for row in rows),
        "interpretation": "Descriptive offline fake-model measurements; no acceptance threshold inferred",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    records = json.loads((args.directory / "samples.json").read_text(encoding="utf-8"))
    print(json.dumps(summarize(records), indent=2))


if __name__ == "__main__":
    main()
