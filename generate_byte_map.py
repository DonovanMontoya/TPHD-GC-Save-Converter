#!/usr/bin/env python3
"""Generate a complete TPHD byte map from the current schema."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from save_schema import TPHD_FIELDS, FieldDef


HD_BODY_SIZE = 0xDF8


def sample_value(data: bytes | None, field: FieldDef) -> str:
    if data is None:
        return ""
    raw = data[field.offset : field.offset + field.size]
    if field.kind == "cstring":
        end = raw.find(b"\x00")
        if end == -1:
            end = len(raw)
        return raw[:end].decode("ascii", errors="replace")
    if field.size <= 16:
        return raw.hex(" ")
    nonzero = sum(b != 0 for b in raw)
    return f"{raw[:16].hex(' ')} ... nonzero={nonzero}/{len(raw)}"


def full_map() -> list[FieldDef]:
    fields = sorted((f for f in TPHD_FIELDS if f.name != "checksum"), key=lambda f: f.offset)
    result: list[FieldDef] = []
    cursor = 0
    for field in fields:
        if field.offset > cursor:
            result.append(
                FieldDef(
                    name=f"gap.0x{cursor:04x}",
                    offset=cursor,
                    size=field.offset - cursor,
                    kind="bytes",
                    confidence="unknown",
                    note="schema gap",
                )
            )
        result.append(field)
        cursor = max(cursor, field.offset + field.size)
    if cursor < HD_BODY_SIZE:
        result.append(
            FieldDef(
                name=f"gap.0x{cursor:04x}",
                offset=cursor,
                size=HD_BODY_SIZE - cursor,
                kind="bytes",
                confidence="unknown",
                note="schema gap",
            )
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a complete TPHD byte map as CSV.")
    parser.add_argument("output", type=Path)
    parser.add_argument("--sample", type=Path, help="Optional ZTPxx.dat sample to include values")
    args = parser.parse_args()

    data = args.sample.read_bytes() if args.sample else None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["start", "end", "size", "confidence", "kind", "name", "note", "sample"])
        for field in full_map():
            writer.writerow(
                [
                    f"0x{field.offset:04x}",
                    f"0x{field.offset + field.size - 1:04x}",
                    f"0x{field.size:x}",
                    field.confidence,
                    field.kind,
                    field.name,
                    field.note,
                    sample_value(data, field),
                ]
            )


if __name__ == "__main__":
    main()
