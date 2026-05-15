#!/usr/bin/env python3
"""Report TPHD save schema coverage by confidence level."""

from __future__ import annotations

from collections import defaultdict

from save_schema import TPHD_FIELDS


HD_BODY_SIZE = 0xDF8


def main() -> None:
    totals: dict[str, int] = defaultdict(int)
    covered = bytearray(HD_BODY_SIZE)

    for field in TPHD_FIELDS:
        if field.name == "checksum":
            continue
        start = field.offset
        end = min(field.offset + field.size, HD_BODY_SIZE)
        if start >= HD_BODY_SIZE:
            continue
        totals[field.confidence] += end - start
        marker = {
            "known": 1,
            "observed": 2,
            "observed_constant": 2,
            "structural": 3,
            "sample_zero": 6,
            "hd_only": 7,
            "unknown": 4,
        }.get(field.confidence, 5)
        for idx in range(start, end):
            covered[idx] = marker

    print(f"TPHD body bytes: 0x{HD_BODY_SIZE:x} ({HD_BODY_SIZE})")
    for confidence in ("known", "observed", "observed_constant", "structural", "sample_zero", "hd_only", "unknown"):
        count = totals.get(confidence, 0)
        print(f"{confidence:10} {count:5} bytes  {count / HD_BODY_SIZE * 100:5.1f}%")

    mapped = totals.get("known", 0) + totals.get("observed", 0) + totals.get("observed_constant", 0) + totals.get("structural", 0)
    classified = mapped + totals.get("sample_zero", 0) + totals.get("hd_only", 0)
    print(f"{'mapped':10} {mapped:5} bytes  {mapped / HD_BODY_SIZE * 100:5.1f}%")
    print(f"{'classified':10} {classified:5} bytes  {classified / HD_BODY_SIZE * 100:5.1f}%")

    unmapped_ranges = []
    start = None
    for idx, marker in enumerate(covered):
        if marker in (0, 4):
            if start is None:
                start = idx
        elif start is not None:
            unmapped_ranges.append((start, idx))
            start = None
    if start is not None:
        unmapped_ranges.append((start, HD_BODY_SIZE))

    print("\nUnmapped/unknown ranges:")
    for start, end in unmapped_ranges:
        print(f"  0x{start:04x}..0x{end - 1:04x} 0x{end - start:03x}")


if __name__ == "__main__":
    main()
