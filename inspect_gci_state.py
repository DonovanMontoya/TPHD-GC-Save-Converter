#!/usr/bin/env python3
"""Inspect GC quest-log state relevant to TPHD conversion probes."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from tphd_to_gci import (
    GC_QUEST_LOG_BODY_SIZE,
    GC_QUEST_LOG_OFFSETS,
    GC_QUEST_LOG_SIZE,
    checksum_pair,
    stored_checksum_pair,
)


STAGES = {
    2: "FARON",
    3: "ELDIN",
    4: "LANAYRU",
    6: "FIELD",
}

EVENT_FLAGS = {
    "TEST_001_kakariko_bridge_portal_hint": 0x0080,
    "M_014_first_castle_warp": 0x0502,
    "M_015_midna_charge": 0x0501,
    "M_018_kakariko_bridge_restored": 0x0620,
    "M_021_first_portal_warp": 0x0604,
    "M_022_forest_temple_warp_hole": 0x0602,
    "M_050_eldin_bridge_disappears": 0x0A20,
    "M_067_midna_riding": 0x0C10,
    "M_077_shadow_crystal": 0x0D04,
    "M_092_eldin_bridge_warped": 0x0F08,
    "F_0540_first_portal_hint": 0x4220,
    "F_0550_wolf_sense": 0x4308,
}

PORTAL_RELEVANT_SWITCHES = {
    2: set(range(128)),
    3: set(range(128)),
    4: set(range(128)),
    6: set(range(128)),
}


@dataclass(frozen=True)
class QuestLog:
    label: str
    body: bytes
    checksum_ok: bool | None


def c_string(data: bytes, offset: int, size: int) -> str:
    raw = data[offset : offset + size]
    end = raw.find(b"\x00")
    if end == -1:
        end = size
    return raw[:end].decode("ascii", errors="replace")


def read_quest_log(path: Path, slot: int, label: str | None = None) -> QuestLog:
    data = path.read_bytes()
    if len(data) == GC_QUEST_LOG_SIZE:
        quest_log = data
    else:
        offset = GC_QUEST_LOG_OFFSETS[slot]
        quest_log = data[offset : offset + GC_QUEST_LOG_SIZE]
    body = quest_log[:GC_QUEST_LOG_BODY_SIZE]
    checksum_ok = None
    if len(quest_log) == GC_QUEST_LOG_SIZE:
        checksum_ok = checksum_pair(body) == stored_checksum_pair(quest_log)
    return QuestLog(label or path.name, body, checksum_ok)


def event_on(body: bytes, flag: int) -> bool:
    return bool(body[0x7F0 + (flag >> 8)] & (flag & 0xFF))


def stage_offset(stage_no: int) -> int:
    return 0x1F0 + stage_no * 0x20


def switch_words(body: bytes, stage_no: int) -> tuple[int, int, int, int]:
    offset = stage_offset(stage_no) + 0x08
    return tuple(int.from_bytes(body[offset + i * 4 : offset + i * 4 + 4], "big") for i in range(4))


def switch_on(body: bytes, stage_no: int, switch_no: int) -> bool:
    words = switch_words(body, stage_no)
    return bool(words[switch_no >> 5] & (1 << (switch_no & 0x1F)))


def active_switches(body: bytes, stage_no: int) -> list[int]:
    return [switch for switch in range(128) if switch_on(body, stage_no, switch)]


def print_summary(log: QuestLog) -> None:
    body = log.body
    print(f"== {log.label} ==")
    if log.checksum_ok is not None:
        print(f"checksum_ok: {log.checksum_ok}")
    print(
        "return_place: "
        f"{c_string(body, 0x058, 8)} point={body[0x060]} room={body[0x061]} "
        f"tail={body[0x062]:02x} {body[0x063]:02x}"
    )
    print(
        "status: "
        f"life={int.from_bytes(body[0x002:0x004], 'big')}/"
        f"{int.from_bytes(body[0x000:0x002], 'big')} "
        f"rupees={int.from_bytes(body[0x004:0x006], 'big')} "
        f"scent=0x{body[0x016]:02x} transform={body[0x01E]}"
    )
    print("events:")
    for name, flag in EVENT_FLAGS.items():
        print(f"  {name:38s} {event_on(body, flag)}")
    print("stage switches:")
    for stage_no, name in STAGES.items():
        switches = active_switches(body, stage_no)
        words = " ".join(f"{word:08x}" for word in switch_words(body, stage_no))
        print(f"  {stage_no:02d} {name:7s} words={words} active={switches}")


def print_diff(left: QuestLog, right: QuestLog) -> None:
    print(f"== diff: {left.label} -> {right.label} ==")
    for name, flag in EVENT_FLAGS.items():
        left_on = event_on(left.body, flag)
        right_on = event_on(right.body, flag)
        if left_on != right_on:
            print(f"event {name}: {left_on} -> {right_on}")

    for stage_no, stage_name in STAGES.items():
        left_switches = set(active_switches(left.body, stage_no))
        right_switches = set(active_switches(right.body, stage_no))
        gained = sorted(right_switches - left_switches)
        lost = sorted(left_switches - right_switches)
        if gained or lost:
            print(f"stage {stage_no:02d} {stage_name}: +{gained} -{lost}")


def parse_ref(value: str) -> tuple[Path, int, str | None]:
    parts = value.split(":", 2)
    path = Path(parts[0])
    slot = int(parts[1], 0) if len(parts) > 1 and parts[1] else 0
    label = parts[2] if len(parts) > 2 else None
    return path, slot, label


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect GC GCI quest-log state relevant to conversion probes.")
    parser.add_argument("gci", type=Path, help="GCI or raw 0xA94 quest-log file")
    parser.add_argument("--slot", type=int, default=0, choices=(0, 1, 2), help="GCI slot to inspect")
    parser.add_argument(
        "--compare",
        action="append",
        default=[],
        metavar="PATH[:SLOT[:LABEL]]",
        help="Reference GCI/raw quest log to diff against. Can be repeated.",
    )
    args = parser.parse_args()

    primary = read_quest_log(args.gci, args.slot)
    print_summary(primary)

    for ref_value in args.compare:
        ref_path, ref_slot, label = parse_ref(ref_value)
        ref = read_quest_log(ref_path, ref_slot, label)
        print()
        print_summary(ref)
        print()
        print_diff(primary, ref)


if __name__ == "__main__":
    main()
