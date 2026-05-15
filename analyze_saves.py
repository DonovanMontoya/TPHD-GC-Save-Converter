#!/usr/bin/env python3
"""Inspect TPHD and GameCube Twilight Princess save fields by schema."""

from __future__ import annotations

import argparse
from pathlib import Path

from save_schema import CONVERSION_RULES, GC_FIELDS, TPHD_FIELDS, FieldDef
from tphd_to_gci import (
    GC_QUEST_LOG_OFFSETS,
    GC_QUEST_LOG_SIZE,
    HD_QUEST_LOG_SIZE,
    checksum_pair,
    c_string,
    stored_checksum_pair,
)


def read_value(data: bytes, field: FieldDef) -> str:
    raw = data[field.offset : field.offset + field.size]
    if field.kind == "u8":
        return f"{raw[0]:#x}"
    if field.kind == "u16be":
        return f"{int.from_bytes(raw, 'big'):#x}"
    if field.kind == "cstring":
        return repr(c_string(data, field.offset, field.size))
    if field.size <= 16:
        return raw.hex(" ")
    return f"{raw[:16].hex(' ')} ..."


def print_schema(name: str, data: bytes, fields: tuple[FieldDef, ...]) -> None:
    print(f"\n{name}")
    for field in fields:
        print(
            f"{field.offset:04x}..{field.offset + field.size - 1:04x} "
            f"{field.size:04x} {field.confidence:10} {field.name:38} {read_value(data, field)}"
        )


def print_checksum(name: str, quest_log: bytes) -> None:
    expected = checksum_pair(quest_log[:-8])
    actual = stored_checksum_pair(quest_log)
    print(f"{name} checksum ok: {expected == actual} calc={expected[0]:08x}/{expected[1]:08x} stored={actual[0]:08x}/{actual[1]:08x}")


def print_conversion_map(hd: bytes, gc: bytes) -> None:
    print("\nConversion Map")
    for rule in CONVERSION_RULES:
        gc_raw = gc[rule.gc_offset : rule.gc_offset + rule.size]
        if rule.source_offset is None:
            src = "<none>"
            src_raw = b""
        else:
            src_raw = hd[rule.source_offset : rule.source_offset + rule.size]
            src = f"0x{rule.source_offset:04x}"
        same = src_raw == gc_raw if src_raw else False
        print(
            f"{rule.name:38} gc=0x{rule.gc_offset:04x} src={src:>8} "
            f"size=0x{rule.size:03x} strategy={rule.strategy:8} "
            f"confidence={rule.confidence:10} sample_equal={same}"
        )
        if rule.note:
            print(f"  note: {rule.note}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze TPHD and GC Twilight Princess save layouts.")
    parser.add_argument("hd_slot", type=Path, help="TPHD ZTPxx.dat")
    parser.add_argument("gci", type=Path, help="GameCube .gci")
    parser.add_argument("--gc-slot", type=int, default=0, choices=(0, 1, 2))
    args = parser.parse_args()

    hd = args.hd_slot.read_bytes()
    if len(hd) != HD_QUEST_LOG_SIZE:
        raise SystemExit(f"HD slot must be 0x{HD_QUEST_LOG_SIZE:x} bytes, got 0x{len(hd):x}")

    gci = args.gci.read_bytes()
    offset = GC_QUEST_LOG_OFFSETS[args.gc_slot]
    gc = gci[offset : offset + GC_QUEST_LOG_SIZE]

    print_checksum("TPHD", hd)
    print_checksum(f"GC slot {args.gc_slot}", gc)
    print_schema("TPHD Observed Fields", hd, TPHD_FIELDS)
    print_schema(f"GC Slot {args.gc_slot} Fields", gc, GC_FIELDS)
    print_conversion_map(hd, gc)


if __name__ == "__main__":
    main()
