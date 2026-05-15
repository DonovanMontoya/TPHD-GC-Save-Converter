#!/usr/bin/env python3
"""Audit Cemu-mapped fields against observed valid GameCube reference slots."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from save_schema import CONVERSION_RULES, ConversionRule
from tphd_to_gci import (
    GC_GCI_SIZE,
    GC_QUEST_LOG_OFFSETS,
    GC_QUEST_LOG_SIZE,
    HD_QUEST_LOG_SIZE,
    checksum_pair,
    c_string,
    stored_checksum_pair,
)


@dataclass(frozen=True)
class ReferenceSlot:
    path: Path
    slot: int
    body: bytes


def valid_gc_slot(quest_log: bytes) -> bool:
    return len(quest_log) == GC_QUEST_LOG_SIZE and checksum_pair(quest_log[:-8]) == stored_checksum_pair(quest_log)


def load_reference_slots(roots: list[Path]) -> list[ReferenceSlot]:
    slots: list[ReferenceSlot] = []
    for root in roots:
        for path in sorted(root.rglob("*.gci")):
            data = path.read_bytes()
            if len(data) != GC_GCI_SIZE:
                continue
            for slot, offset in enumerate(GC_QUEST_LOG_OFFSETS):
                quest_log = data[offset : offset + GC_QUEST_LOG_SIZE]
                if valid_gc_slot(quest_log):
                    slots.append(ReferenceSlot(path, slot, quest_log[:-8]))
    return slots


def auditable_rule(rule: ConversionRule) -> bool:
    if rule.strategy in ("template", "drop") or rule.source_offset is None:
        return False
    return rule.confidence in ("observed", "load_unsafe")


def normalized_source_bytes(hd: bytes, rule: ConversionRule) -> bytes:
    assert rule.source_offset is not None
    if rule.strategy == "cstring":
        out = bytearray(b"\x00" * rule.size)
        raw = hd[rule.source_offset : rule.source_offset + rule.size]
        end = raw.find(b"\x00")
        if end == -1:
            end = rule.size
        out[:end] = raw[:end]
        return bytes(out)
    return hd[rule.source_offset : rule.source_offset + rule.size]


def stage_string_for_rule(data: bytes, rule: ConversionRule, source: bool) -> str:
    offset = rule.source_offset if source else rule.gc_offset
    if offset is None:
        return ""
    if rule.name == "player.return_place":
        return c_string(data, offset, 8)
    if rule.name in {"player.horse_place", "player.field_last_stay", "player.last_mark"}:
        return c_string(data, offset + 0x0E, 8)
    return c_string(data, offset, 8)


def summarize_rule(rule: ConversionRule, hd: bytes, references: list[ReferenceSlot]) -> dict[str, str | int]:
    assert rule.source_offset is not None
    src = normalized_source_bytes(hd, rule)
    ref_values = [slot.body[rule.gc_offset : rule.gc_offset + rule.size] for slot in references]
    exact_matches = sum(value == src for value in ref_values)
    unique_sequences = len(set(ref_values))

    positions_outside = []
    for index, byte in enumerate(src):
        observed = {value[index] for value in ref_values}
        if byte not in observed:
            positions_outside.append(index)

    min_distance = min(
        (sum(a != b for a, b in zip(src, value, strict=True)) for value in ref_values),
        default=rule.size,
    )
    nonzero = sum(byte != 0 for byte in src)
    first_outside = " ".join(f"{offset:02x}" for offset in positions_outside[:24])
    if len(positions_outside) > 24:
        first_outside += " ..."

    return {
        "rule": rule.name,
        "confidence": rule.confidence,
        "gc_offset": f"0x{rule.gc_offset:03x}",
        "hd_offset": f"0x{rule.source_offset:03x}",
        "size": rule.size,
        "hd_stage": stage_string_for_rule(hd, rule, True),
        "exact_reference_matches": exact_matches,
        "reference_unique_sequences": unique_sequences,
        "min_byte_distance_to_reference": min_distance,
        "hd_nonzero_bytes": nonzero,
        "positions_outside_reference": len(positions_outside),
        "first_outside_relative_offsets": first_outside,
        "hd_bytes": src.hex(" ") if rule.size <= 0x50 else src[:0x50].hex(" ") + " ...",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare mapped TPHD fields with observed GC reference ranges.")
    parser.add_argument("cemu_slot", type=Path, help="TPHD ZTPxx.dat to audit")
    parser.add_argument("output", type=Path)
    parser.add_argument("reference_roots", nargs="+", type=Path)
    args = parser.parse_args()

    hd = args.cemu_slot.read_bytes()
    if len(hd) != HD_QUEST_LOG_SIZE or checksum_pair(hd[:-8]) != stored_checksum_pair(hd):
        raise SystemExit(f"{args.cemu_slot} is not a valid TPHD quest-log slot")

    references = load_reference_slots(args.reference_roots)
    if not references:
        raise SystemExit("No valid GC reference slots found")

    rows = [summarize_rule(rule, hd, references) for rule in CONVERSION_RULES if auditable_rule(rule)]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    risky = [
        row for row in rows
        if int(row["positions_outside_reference"]) > 0 and not str(row["rule"]).startswith("player.info.")
    ]
    print(f"Loaded {len(references)} valid GC reference slots")
    print(f"Wrote {args.output}")
    print("Mapped groups with bytes outside observed GC references:")
    for row in risky:
        print(
            f"  {row['rule']}: {row['positions_outside_reference']} positions outside, "
            f"min distance {row['min_byte_distance_to_reference']}"
        )


if __name__ == "__main__":
    main()
