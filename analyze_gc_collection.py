#!/usr/bin/env python3
"""Summarize GameCube Twilight Princess GCI saves by quest-log slot."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from tphd_to_gci import GC_GCI_SIZE, GC_QUEST_LOG_OFFSETS, GC_QUEST_LOG_SIZE, checksum_pair, c_string, stored_checksum_pair


def read_u16be(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], "big")


def annotation_file(path: Path) -> Path | None:
    for name in ("List with Annotations.txt", "List of Saves.txt"):
        candidate = path.parent / name
        if candidate.exists():
            return candidate
    return None


def slot_label(path: Path, slot: int) -> str:
    annotations = annotation_file(path)
    if annotations is None:
        return ""
    index_match = re.match(r"(\d+)", path.name)
    if not index_match:
        return ""
    index = index_match.group(1)
    lines = [line.strip() for line in annotations.read_text(errors="replace").splitlines()]
    for i, line in enumerate(lines):
        if line.startswith(index + " ") or line.startswith(index + ":"):
            labels = []
            for next_line in lines[i + 1 :]:
                if not next_line:
                    continue
                if re.match(r"\d+(?:\b|:)", next_line):
                    break
                labels.append(next_line.removeprefix("-").strip())
                if len(labels) == 3:
                    break
            return labels[slot] if slot < len(labels) else ""
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize GameCube TP GCI slots.")
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    files = sorted(args.root.rglob("*.gci"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "path",
                "game_id",
                "slot",
                "label",
                "checksum_ok",
                "player_name",
                "horse_name",
                "return_stage",
                "max_life",
                "life",
                "rupees",
                "max_oil",
                "oil",
                "select_items",
                "mix_items",
                "equipment",
                "wallet_size",
                "transform",
                "nonzero",
            ]
        )
        for path in files:
            data = path.read_bytes()
            if len(data) != GC_GCI_SIZE:
                continue
            game_id = data[:6].decode("ascii", errors="replace")
            for slot, offset in enumerate(GC_QUEST_LOG_OFFSETS):
                q = data[offset : offset + GC_QUEST_LOG_SIZE]
                writer.writerow(
                    [
                        str(path),
                        game_id,
                        slot,
                        slot_label(path, slot),
                        checksum_pair(q[:-8]) == stored_checksum_pair(q),
                        c_string(q, 0x1B4, 16),
                        c_string(q, 0x1C5, 16),
                        c_string(q, 0x58, 8),
                        read_u16be(q, 0x00),
                        read_u16be(q, 0x02),
                        read_u16be(q, 0x04),
                        read_u16be(q, 0x06),
                        read_u16be(q, 0x08),
                        q[0x0B:0x0F].hex(" "),
                        q[0x0F:0x13].hex(" "),
                        q[0x13:0x19].hex(" "),
                        q[0x19],
                        q[0x1E],
                        sum(b != 0 for b in q[:-8]),
                    ]
                )
    print(f"Wrote {args.output} for {len(files)} GCI files")


if __name__ == "__main__":
    main()
