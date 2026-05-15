#!/usr/bin/env python3
"""Twilight Princess HD Cemu save -> GameCube/Dolphin GCI converter.

This is a conservative converter. TPHD changed enough save layout that blindly
copying its 0xE00 quest log into the GameCube 0xA94 quest log produces a file
that appears in Dolphin but does not load. The converter therefore starts from
a known-good GameCube GCI template and overlays only mapped TPHD fields.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from save_schema import CONVERSION_RULES, ConversionRule


HD_QUEST_LOG_SIZE = 0xE00
GC_GCI_SIZE = 0x8040
GC_QUEST_LOG_SIZE = 0xA94
GC_QUEST_LOG_BODY_SIZE = GC_QUEST_LOG_SIZE - 8
GC_QUEST_LOG_OFFSETS = (0x4048, 0x4ADC, 0x5570)
GC_TEMPLATE_CANDIDATES = (
    Path("GameCubeSave/Card A/01-GZ2E-gczelda2.gci"),
    Path("01-GZ2E-gczelda2.gci"),
)
GC_SENSE_EVENT = 0x4308
GC_CHILDREN_SCENT_EVENT = 0x2240
GC_ILIA_SCENT_EVENT = 0x2220
SMELL_ITEMS = {
    0xB0: "Ilia pouch scent",
    0xB2: "Poe scent",
    0xB3: "fish scent",
    0xB4: "children scent",
    0xB5: "medicine scent",
}


@dataclass
class FieldResult:
    name: str
    status: str
    detail: str


@dataclass
class SlotReport:
    hd_slot: int
    gc_slot: int
    player_name: str
    horse_name: str
    max_life: int
    current_life: int
    rupees: int
    fields: list[FieldResult] = field(default_factory=list)


def checksum_pair(data: bytes) -> tuple[int, int]:
    total_raw = sum(data)
    total = total_raw & 0xFFFFFFFF
    negative = (-(total_raw + len(data))) & 0xFFFFFFFF
    return total, negative


def stored_checksum_pair(quest_log: bytes) -> tuple[int, int]:
    return (
        int.from_bytes(quest_log[-8:-4], "big"),
        int.from_bytes(quest_log[-4:], "big"),
    )


def read_u16be(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], "big")


def c_string(data: bytes, offset: int, size: int) -> str:
    raw = data[offset : offset + size]
    end = raw.find(b"\x00")
    if end == -1:
        end = size
    return raw[:end].decode("ascii", errors="replace")


def copy_c_string(dst: bytearray, dst_offset: int, src: bytes, src_offset: int, size: int) -> None:
    dst[dst_offset : dst_offset + size] = b"\x00" * size
    raw = src[src_offset : src_offset + size]
    end = raw.find(b"\x00")
    if end == -1:
        end = size
    dst[dst_offset : dst_offset + end] = raw[:end]


def set_event_bit(body: bytearray, event_flag: int) -> None:
    body[0x7F0 + (event_flag >> 8)] |= event_flag & 0xFF


def set_item_first_bit(body: bytearray, item_id: int) -> None:
    word_offset = 0x0CC + (item_id // 32) * 4
    bit = item_id % 32
    value = int.from_bytes(body[word_offset : word_offset + 4], "big")
    value |= 1 << bit
    body[word_offset : word_offset + 4] = value.to_bytes(4, "big")


def normalize_wolf_abilities(body: bytearray, hd_slot: bytes, report: SlotReport, profile: str) -> None:
    if profile not in ("balanced", "progress"):
        return

    scent_item = hd_slot[0x018]
    if scent_item not in SMELL_ITEMS:
        return

    body[0x016] = scent_item
    body[0x00D] = scent_item
    set_item_first_bit(body, scent_item)
    set_event_bit(body, GC_SENSE_EVENT)

    if scent_item == 0xB0:
        set_event_bit(body, GC_ILIA_SCENT_EVENT)
    elif scent_item == 0xB4:
        set_event_bit(body, GC_CHILDREN_SCENT_EVENT)

    report.fields.append(
        FieldResult(
            "player.wolf_ability_normalization",
            "derived",
            f"mapped {SMELL_ITEMS[scent_item]} from HD 0x018; set GC scent equip, item-first bit, and sense flag 0x4308",
        )
    )


def validate_hd_slot(data: bytes, label: str) -> None:
    if len(data) != HD_QUEST_LOG_SIZE:
        raise ValueError(f"{label} must be 0xE00 bytes, got {len(data):#x}")

    expected = checksum_pair(data[:-8])
    actual = stored_checksum_pair(data)
    if expected != actual:
        raise ValueError(
            f"{label} checksum mismatch: "
            f"expected {expected[0]:08x}/{expected[1]:08x}, "
            f"found {actual[0]:08x}/{actual[1]:08x}"
        )


def validate_gci_template(data: bytes) -> None:
    if len(data) != GC_GCI_SIZE:
        raise ValueError(f"GameCube GCI template must be 0x8040 bytes, got {len(data):#x}")

    game_id = data[:6].decode("ascii", errors="replace")
    if not game_id.startswith("GZ2"):
        raise ValueError(f"GCI template does not look like Twilight Princess: game id {game_id!r}")


def find_default_template() -> Path | None:
    for candidate in GC_TEMPLATE_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def find_cemu_slots(cemu_save: Path) -> list[Path]:
    if cemu_save.is_file():
        return [cemu_save]

    candidates = sorted(cemu_save.rglob("ZTP0[0-2].dat"))
    if candidates:
        return candidates

    candidates = sorted(cemu_save.rglob("ZTP*.dat"))
    if candidates:
        return candidates

    raise FileNotFoundError(f"No ZTPxx.dat slot files found under {cemu_save}")


def parse_slot_index(path: Path) -> int:
    stem = path.stem.upper()
    if stem.startswith("ZTP") and stem[3:].isdigit():
        return int(stem[3:])
    return 0


def conversion_rule_enabled(rule: ConversionRule, profile: str) -> bool:
    if rule.strategy in ("template", "drop"):
        return False
    if rule.confidence in ("known", "observed"):
        return profile in ("balanced", "progress") or rule.name.startswith("player.info.") or rule.name.startswith("player.status_a.")
    if rule.confidence == "structural":
        return profile == "progress"
    return False


def apply_conversion_rule(body: bytearray, hd_slot: bytes, report: SlotReport, rule: ConversionRule) -> None:
    if rule.source_offset is None:
        report.fields.append(FieldResult(rule.name, rule.strategy, rule.note or "kept from template"))
        return

    if rule.strategy == "copy":
        body[rule.gc_offset : rule.gc_offset + rule.size] = hd_slot[
            rule.source_offset : rule.source_offset + rule.size
        ]
        report.fields.append(
            FieldResult(
                rule.name,
                rule.confidence,
                f"copied 0x{rule.size:x} bytes from HD 0x{rule.source_offset:x} to GC 0x{rule.gc_offset:x}",
            )
        )
    elif rule.strategy == "cstring":
        copy_c_string(body, rule.gc_offset, hd_slot, rule.source_offset, rule.size)
        report.fields.append(
            FieldResult(
                rule.name,
                rule.confidence,
                f"copied string from HD 0x{rule.source_offset:x} to GC 0x{rule.gc_offset:x}",
            )
        )
    else:
        raise ValueError(f"Unsupported conversion strategy {rule.strategy!r}")


def build_mapped_body(hd_slot: bytes, gc_template_quest_log: bytes, hd_slot_index: int, gc_slot: int, profile: str) -> tuple[bytes, SlotReport]:
    """Build a GC quest-log body using targeted TPHD fields."""

    body = bytearray(gc_template_quest_log[:GC_QUEST_LOG_BODY_SIZE])
    report = SlotReport(
        hd_slot=hd_slot_index,
        gc_slot=gc_slot,
        player_name=c_string(hd_slot, 0x1B4, 16),
        horse_name=c_string(hd_slot, 0x1C5, 16),
        max_life=read_u16be(hd_slot, 0x02),
        current_life=read_u16be(hd_slot, 0x04),
        rupees=read_u16be(hd_slot, 0x06),
    )

    for rule in CONVERSION_RULES:
        if conversion_rule_enabled(rule, profile):
            apply_conversion_rule(body, hd_slot, report, rule)

    normalize_wolf_abilities(body, hd_slot, report, profile)

    report.fields.extend(
        [
            FieldResult("player_config", "template", "kept from GC template; TPHD options are not byte-compatible with GC options"),
            FieldResult("reserve", "template", "kept from GC template; TPHD stores extra stage/HD data here"),
            FieldResult("profile", profile, "safe copies only identity/basic stats; balanced adds inventory/location; progress adds event/stage flags"),
            FieldResult("hd_extra_tail", "dropped", "TPHD bytes 0xA94..0xDF7 have no GC quest-log destination"),
        ]
    )

    return bytes(body), report


def patch_slot(out: bytearray, body: bytes, slot: int) -> None:
    offset = GC_QUEST_LOG_OFFSETS[slot]
    out[offset : offset + GC_QUEST_LOG_BODY_SIZE] = body
    csum, nsum = checksum_pair(body)
    out[offset + GC_QUEST_LOG_BODY_SIZE : offset + GC_QUEST_LOG_SIZE] = (
        csum.to_bytes(4, "big") + nsum.to_bytes(4, "big")
    )


def verify_gc_slot(gci: bytes, slot: int) -> bool:
    offset = GC_QUEST_LOG_OFFSETS[slot]
    quest_log = gci[offset : offset + GC_QUEST_LOG_SIZE]
    return checksum_pair(quest_log[:-8]) == stored_checksum_pair(quest_log)


def convert_cemu_save(cemu_save: Path, gci_template: Path, output: Path, slots: Iterable[int] | None, profile: str) -> list[SlotReport]:
    template = gci_template.read_bytes()
    validate_gci_template(template)
    out = bytearray(template)

    reports: list[SlotReport] = []
    allowed_slots = set(slots) if slots is not None else None

    for slot_path in find_cemu_slots(cemu_save):
        hd_index = parse_slot_index(slot_path)
        if hd_index not in (0, 1, 2):
            continue
        if allowed_slots is not None and hd_index not in allowed_slots:
            continue

        hd_slot = slot_path.read_bytes()
        validate_hd_slot(hd_slot, str(slot_path))
        template_offset = GC_QUEST_LOG_OFFSETS[hd_index]
        template_quest_log = template[template_offset : template_offset + GC_QUEST_LOG_SIZE]
        body, report = build_mapped_body(hd_slot, template_quest_log, hd_index, hd_index, profile)
        patch_slot(out, body, hd_index)

        if not verify_gc_slot(out, hd_index):
            raise RuntimeError(f"Internal error: generated slot {hd_index} checksum is invalid")
        reports.append(report)

    if not reports:
        raise ValueError("No selected TPHD slots were converted")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(out)
    return reports


def report_to_json(reports: list[SlotReport]) -> str:
    return json.dumps(
        [
            {
                "hd_slot": report.hd_slot,
                "gc_slot": report.gc_slot,
                "player_name": report.player_name,
                "horse_name": report.horse_name,
                "max_life": report.max_life,
                "current_life": report.current_life,
                "rupees": report.rupees,
                "fields": [field.__dict__ for field in report.fields],
            }
            for report in reports
        ],
        indent=2,
    )


def print_report(reports: list[SlotReport]) -> None:
    for report in reports:
        print(f"Slot {report.hd_slot} -> {report.gc_slot}")
        print(f"  Player: {report.player_name or '<blank>'}")
        print(f"  Horse: {report.horse_name or '<blank>'}")
        print(f"  Health: {report.current_life}/{report.max_life}")
        print(f"  Rupees: {report.rupees}")
        for field_result in report.fields:
            print(f"  [{field_result.status}] {field_result.name}: {field_result.detail}")


def parse_slot_list(value: str) -> list[int]:
    slots = []
    for part in value.split(","):
        slot = int(part.strip(), 0)
        if slot not in (0, 1, 2):
            raise argparse.ArgumentTypeError("slots must be 0, 1, or 2")
        slots.append(slot)
    return slots


def main() -> None:
    default_template = find_default_template()
    parser = argparse.ArgumentParser(
        description="Convert a Twilight Princess HD Cemu save folder or ZTPxx.dat into a Dolphin GameCube .gci."
    )
    parser.add_argument("cemu_save", type=Path, help="Cemu save folder or a TPHD ZTPxx.dat file")
    parser.add_argument("output", type=Path, help="Converted Dolphin .gci output path")
    parser.add_argument(
        "--template",
        type=Path,
        default=default_template,
        help="Existing TP GameCube .gci to use as the metadata/template base",
    )
    parser.add_argument("--slots", type=parse_slot_list, help="Comma-separated TPHD slot indexes to convert, default: all found")
    parser.add_argument(
        "--profile",
        choices=("safe", "balanced", "progress"),
        default="safe",
        help="Conversion depth. safe is the current load-tested default; balanced/progress preserve more state but need validation.",
    )
    parser.add_argument("--json-report", type=Path, help="Write the conversion report as JSON")
    args = parser.parse_args()

    if args.template is None:
        raise SystemExit("No GCI template found. Pass --template /path/to/01-GZ2E-gczelda2.gci")

    reports = convert_cemu_save(args.cemu_save, args.template, args.output, args.slots, args.profile)
    print(f"Wrote {args.output} ({GC_GCI_SIZE:#x} bytes)")
    print_report(reports)

    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(report_to_json(reports) + "\n", encoding="utf-8")
        print(f"Wrote report {args.json_report}")


if __name__ == "__main__":
    main()
