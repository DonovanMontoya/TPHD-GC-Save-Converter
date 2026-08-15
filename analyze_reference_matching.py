#!/usr/bin/env python3
"""Evaluate automatic GC-reference matching across a TPHD save collection."""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path

from gc_reference_matcher import (
    confidence_margin,
    load_reference_hints,
    load_reference_slots,
    rank_references,
)
from tphd_to_gci import c_string, validate_hd_slot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cemu_root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("reference_roots", nargs="+", type=Path)
    parser.add_argument("--min-margin", type=int, default=50)
    parser.add_argument("--reference-hints", type=Path)
    args = parser.parse_args()

    references = load_reference_slots(args.reference_roots)
    if not references:
        raise SystemExit("No valid GC reference slots found")
    hints = load_reference_hints(args.reference_hints) if args.reference_hints else {}

    rows: list[dict[str, str | int | bool]] = []
    for path in sorted(args.cemu_root.rglob("ZTP*.dat")):
        hd = path.read_bytes()
        validate_hd_slot(hd, str(path))
        matches = rank_references(hd, references)
        best = matches[0]
        second = matches[1] if len(matches) > 1 else matches[0]
        margin = confidence_margin(matches)
        hd_stage = c_string(hd, 0x058, 8)
        hint = hints.get(hashlib.sha256(hd).hexdigest())
        decision = "ranked"
        note = ""
        accepted = best.stage == hd_stage and margin >= args.min_margin
        if hint is not None and hint.unsupported_reason is not None:
            decision = "unsupported"
            note = hint.unsupported_reason
            accepted = False
        elif hint is not None:
            decision = "curated"
            note = hint.note
            accepted = True
            best = next(
                match
                for match in matches
                if any(
                    reference.file_sha256 == hint.reference_sha256
                    and reference.slot == hint.reference_slot
                    and str(reference.path) == match.path
                    and reference.slot == match.slot
                    for reference in references
                )
            )
        exact_stage = best.stage == hd_stage
        rows.append(
            {
                "path": str(path),
                "hd_stage": hd_stage,
                "hd_point": hd[0x060],
                "hd_room": hd[0x061],
                "decision": decision,
                "accepted": accepted,
                "note": note,
                "exact_stage": exact_stage,
                "score": best.total,
                "margin": margin,
                "reference_path": best.path,
                "reference_slot": best.slot,
                "reference_label": best.label,
                "reference_stage": best.stage,
                "reference_point": best.point,
                "reference_room": best.room,
                "runner_up_score": second.total,
                "runner_up_path": second.path,
                "runner_up_slot": second.slot,
                "runner_up_label": second.label,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    accepted = sum(bool(row["accepted"]) for row in rows)
    curated = sum(row["decision"] == "curated" for row in rows)
    unsupported = sum(row["decision"] == "unsupported" for row in rows)
    ranked = len(rows) - curated - unsupported
    print(f"References: {len(references)}")
    print(f"TPHD slots: {len(rows)}")
    print(f"Accepted: {accepted}")
    print(f"Curated: {curated}")
    print(f"Unsupported: {unsupported}")
    print(f"Ranked without a hint: {ranked}")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
