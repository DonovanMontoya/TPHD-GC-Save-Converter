#!/usr/bin/env python3
"""Summarize a collection of TPHD Cemu ZTP saves."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from save_schema import TPHD_FIELDS
from tphd_to_gci import HD_QUEST_LOG_SIZE, checksum_pair, c_string, stored_checksum_pair


def valid_slot(data: bytes) -> bool:
    return len(data) == HD_QUEST_LOG_SIZE and checksum_pair(data[:-8]) == stored_checksum_pair(data)


def field_value(data: bytes, offset: int, size: int, kind: str) -> str:
    raw = data[offset : offset + size]
    if kind == "u8":
        return str(raw[0])
    if kind == "u16be":
        return str(int.from_bytes(raw, "big"))
    if kind == "cstring":
        return c_string(data, offset, size)
    if size <= 8:
        return raw.hex(" ")
    return raw.hex()


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize all valid TPHD ZTP saves under a folder.")
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    files = sorted(args.root.rglob("ZTP0*.dat"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = [f for f in TPHD_FIELDS if f.name != "checksum"]
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["path", "slot", "valid", "nonzero", "stage", "current_stage"]
            + [field.name for field in fields]
        )
        for path in files:
            data = path.read_bytes()
            ok = valid_slot(data)
            row = [
                str(path),
                path.stem,
                ok,
                sum(b != 0 for b in data[:-8]) if ok else "",
                c_string(data, 0x58, 8) if ok else "",
                c_string(data, 0x8F0, 8) if ok else "",
            ]
            if ok:
                row.extend(field_value(data, field.offset, field.size, field.kind) for field in fields)
            else:
                row.extend("" for _ in fields)
            writer.writerow(row)

    print(f"Wrote {args.output} for {len(files)} ZTP files")


if __name__ == "__main__":
    main()
