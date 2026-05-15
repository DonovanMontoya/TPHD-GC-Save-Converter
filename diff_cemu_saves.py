#!/usr/bin/env python3
"""Diff two TPHD ZTPxx.dat files and annotate changes with the schema."""

from __future__ import annotations

import argparse
from pathlib import Path

from save_schema import TPHD_FIELDS, FieldDef
from tphd_to_gci import HD_QUEST_LOG_SIZE, checksum_pair, stored_checksum_pair


def validate(path: Path, data: bytes) -> None:
    if len(data) != HD_QUEST_LOG_SIZE:
        raise SystemExit(f"{path} must be 0x{HD_QUEST_LOG_SIZE:x} bytes, got 0x{len(data):x}")
    if checksum_pair(data[:-8]) != stored_checksum_pair(data):
        raise SystemExit(f"{path} checksum is invalid")


def field_for(offset: int) -> FieldDef | None:
    for field in TPHD_FIELDS:
        if field.offset <= offset < field.offset + field.size:
            return field
    return None


def changed_runs(a: bytes, b: bytes) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start = None
    for idx, (left, right) in enumerate(zip(a[:-8], b[:-8])):
        if left != right and start is None:
            start = idx
        elif left == right and start is not None:
            runs.append((start, idx))
            start = None
    if start is not None:
        runs.append((start, len(a) - 8))
    return runs


def main() -> None:
    parser = argparse.ArgumentParser(description="Diff two TPHD save slots and annotate changed byte ranges.")
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--context", type=int, default=8, help="Bytes of hex context on each side")
    args = parser.parse_args()

    before = args.before.read_bytes()
    after = args.after.read_bytes()
    validate(args.before, before)
    validate(args.after, after)

    runs = changed_runs(before, after)
    print(f"Changed runs: {len(runs)}")
    for start, end in runs:
        field = field_for(start)
        label = field.name if field else "<unknown>"
        confidence = field.confidence if field else "unknown"
        print(f"0x{start:04x}..0x{end - 1:04x} size=0x{end - start:x} field={label} confidence={confidence}")
        ctx_start = max(0, start - args.context)
        ctx_end = min(len(before) - 8, end + args.context)
        print(f"  before: {before[ctx_start:ctx_end].hex(' ')}")
        print(f"  after : {after[ctx_start:ctx_end].hex(' ')}")


if __name__ == "__main__":
    main()
