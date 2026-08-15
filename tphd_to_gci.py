#!/usr/bin/env python3
"""Twilight Princess HD Cemu save -> GameCube/Dolphin GCI converter.

This is a conservative converter. TPHD changed enough save layout that blindly
copying its 0xE00 quest log into the GameCube 0xA94 quest log produces a file
that appears in Dolphin but does not load. The converter therefore starts from
a known-good GameCube GCI template and overlays only mapped TPHD fields.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from save_schema import CONVERSION_RULES, LOCATION_RULE_NAMES, ConversionRule


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
GC_MIDNA_CHARGE_EVENT = 0x0501
GC_MIDNA_RIDING_EVENT = 0x0C10
GC_CHILDREN_SCENT_EVENT = 0x2240
GC_ILIA_SCENT_EVENT = 0x2220
SMELL_ITEMS = {
    0xB0: "Ilia pouch scent",
    0xB2: "Poe scent",
    0xB3: "fish scent",
    0xB4: "children scent",
    0xB5: "medicine scent",
}
PROFILES = ("safe", "balanced", "progress")
AUTO_REFERENCE_OVERLAY_RULES = {
    "player.status_a.max_life",
    "player.status_a.life",
    "player.status_a.rupees",
    "player.status_a.max_oil",
    "player.status_a.oil",
    "player.info.total_time",
    "player.info.death_count",
    "player.info.player_name",
    "player.info.horse_name",
    "player.info.clear_count",
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
    set_event_bit(body, GC_MIDNA_CHARGE_EVENT)
    set_event_bit(body, GC_MIDNA_RIDING_EVENT)

    if scent_item == 0xB0:
        set_event_bit(body, GC_ILIA_SCENT_EVENT)
    elif scent_item == 0xB4:
        set_event_bit(body, GC_CHILDREN_SCENT_EVENT)

    report.fields.append(
        FieldResult(
            "player.wolf_ability_normalization",
            "derived",
            f"mapped {SMELL_ITEMS[scent_item]} from HD 0x018; set GC scent equip, item-first bit, sense flag 0x4308, Midna charge flag 0x0501, and Midna riding flag 0x0c10",
        )
    )


def apply_gc_state_reference(
    body: bytearray,
    reference_body: bytes,
    report: SlotReport,
    detail: str | None = None,
    coherent_scene: bool = False,
) -> None:
    if coherent_scene:
        body[:] = reference_body
    else:
        body[0x058:0x064] = reference_body[0x058:0x064]
        body[0x1F0:0x5F0] = reference_body[0x1F0:0x5F0]
        body[0x7F0:0x8F0] = reference_body[0x7F0:0x8F0]
    report.fields.append(
        FieldResult(
            "scene.gc_state_reference",
            "reference",
            detail
            or "copied return_place, stage memory, and event flags from paired GC state reference; TPHD stats/inventory remain mapped separately",
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
    # Location structs are a mutually consistent bundle. Copying part of it from
    # TPHD while return_place comes from the GC template or a paired reference
    # yields a scene state that never existed in either save, so the whole
    # bundle stays GC-native until a paired-save diff validates a translation.
    if rule.name in LOCATION_RULE_NAMES:
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


def build_mapped_body(
    hd_slot: bytes,
    gc_template_quest_log: bytes,
    hd_slot_index: int,
    gc_slot: int,
    profile: str,
    gc_state_reference_body: bytes | None = None,
    gc_state_reference_detail: str | None = None,
    gc_state_reference_coherent_scene: bool = False,
) -> tuple[bytes, SlotReport]:
    """Build a GC quest-log body using targeted TPHD fields."""

    if profile not in PROFILES:
        raise ValueError(f"Unknown conversion profile {profile!r}")
    if len(hd_slot) != HD_QUEST_LOG_SIZE:
        raise ValueError(f"TPHD slot must be 0x{HD_QUEST_LOG_SIZE:x} bytes")
    if len(gc_template_quest_log) != GC_QUEST_LOG_SIZE:
        raise ValueError(f"GC template quest log must be 0x{GC_QUEST_LOG_SIZE:x} bytes")
    if gc_state_reference_body is not None and len(gc_state_reference_body) != GC_QUEST_LOG_BODY_SIZE:
        raise ValueError(f"GC state reference body must be 0x{GC_QUEST_LOG_BODY_SIZE:x} bytes")

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

    if gc_state_reference_body is not None and gc_state_reference_coherent_scene:
        apply_gc_state_reference(
            body,
            gc_state_reference_body,
            report,
            gc_state_reference_detail,
            gc_state_reference_coherent_scene,
        )
        for rule in CONVERSION_RULES:
            if rule.name in AUTO_REFERENCE_OVERLAY_RULES:
                apply_conversion_rule(body, hd_slot, report, rule)
    else:
        for rule in CONVERSION_RULES:
            if conversion_rule_enabled(rule, profile):
                apply_conversion_rule(body, hd_slot, report, rule)

        if gc_state_reference_body is not None:
            apply_gc_state_reference(
                body,
                gc_state_reference_body,
                report,
                gc_state_reference_detail,
                gc_state_reference_coherent_scene,
            )

    if not gc_state_reference_coherent_scene:
        normalize_wolf_abilities(body, hd_slot, report, profile)

    # Location provenance has three distinct cases. An explicit reference grafts
    # only return_place, so the bundle is genuinely mixed and must not be
    # reported as wholly template-sourced.
    never_grafted = "; TPHD location state is not grafted without a validated translation"
    if gc_state_reference_coherent_scene:
        location_status = "reference"
        location_detail = "kept " + ", ".join(sorted(LOCATION_RULE_NAMES)) + " from coherent GC reference"
    elif gc_state_reference_body is not None:
        location_status = "mixed"
        location_detail = (
            "player.return_place from paired GC reference; "
            + ", ".join(sorted(LOCATION_RULE_NAMES - {"player.return_place"}))
            + " from GC template"
            + never_grafted
        )
    else:
        location_status = "template"
        location_detail = "kept " + ", ".join(sorted(LOCATION_RULE_NAMES)) + " from GC template" + never_grafted

    report.fields.extend(
        [
            FieldResult("location_structs", location_status, location_detail),
            FieldResult(
                "player_config",
                "reference" if gc_state_reference_coherent_scene else "template",
                "kept from coherent GC reference"
                if gc_state_reference_coherent_scene
                else "kept from GC template; TPHD options are not byte-compatible with GC options",
            ),
            FieldResult(
                "reserve",
                "reference" if gc_state_reference_coherent_scene else "template",
                "kept from coherent GC reference"
                if gc_state_reference_coherent_scene
                else "kept from GC template; TPHD stores extra stage/HD data here",
            ),
            FieldResult(
                "profile",
                profile,
                "safe copies only identity/basic stats; balanced adds inventory/location; "
                "progress adds event/stage flags",
            ),
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


def quest_log_body_from_gci(data: bytes, slot: int) -> bytes:
    if slot not in (0, 1, 2):
        raise ValueError("Reference GCI slot must be 0, 1, or 2")
    validate_gci_template(data)
    offset = GC_QUEST_LOG_OFFSETS[slot]
    quest_log = data[offset : offset + GC_QUEST_LOG_SIZE]
    if len(quest_log) != GC_QUEST_LOG_SIZE:
        raise ValueError(f"Reference GCI slot {slot} is incomplete")
    if checksum_pair(quest_log[:-8]) != stored_checksum_pair(quest_log):
        raise ValueError(f"Reference GCI slot {slot} checksum is invalid")
    return quest_log[:GC_QUEST_LOG_BODY_SIZE]


def convert_cemu_save(
    cemu_save: Path,
    gci_template: Path,
    output: Path,
    slots: Iterable[int] | None,
    profile: str,
    gc_state_reference: Path | None = None,
    gc_state_reference_slot: int = 0,
    auto_gc_state_reference_roots: Iterable[Path] | None = None,
    auto_reference_min_margin: int = 50,
    auto_reference_hints: Path | None = None,
) -> list[SlotReport]:
    template = gci_template.read_bytes()
    validate_gci_template(template)
    out = bytearray(template)
    gc_state_reference_body = (
        quest_log_body_from_gci(gc_state_reference.read_bytes(), gc_state_reference_slot)
        if gc_state_reference is not None
        else None
    )
    auto_references = None
    curated_hints = {}
    if auto_gc_state_reference_roots is not None:
        from gc_reference_matcher import load_reference_hints, load_reference_slots

        auto_references = load_reference_slots(list(auto_gc_state_reference_roots))
        if not auto_references:
            raise ValueError("No valid GC slots found under automatic reference roots")
        if auto_reference_hints is not None:
            curated_hints = load_reference_hints(auto_reference_hints)

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
        slot_reference_body = gc_state_reference_body
        slot_reference_detail = None
        slot_reference_coherent_scene = False
        if auto_references is not None:
            from gc_reference_matcher import confidence_margin, rank_references

            hd_sha256 = hashlib.sha256(hd_slot).hexdigest()
            hint = curated_hints.get(hd_sha256)
            if hint is not None:
                if hint.unsupported_reason is not None:
                    raise ValueError(
                        f"Curated reference manifest rejects TPHD slot {hd_index}: "
                        f"{hint.unsupported_reason}"
                    )
                selected = next(
                    (
                        reference
                        for reference in auto_references
                        if reference.file_sha256 == hint.reference_sha256
                        and reference.slot == hint.reference_slot
                    ),
                    None,
                )
                if selected is None:
                    raise ValueError(
                        f"Curated GC reference {hint.reference_sha256} slot {hint.reference_slot} "
                        "is not present under the automatic reference roots"
                    )
                slot_reference_detail = (
                    f"selected curated reference {selected.path} slot {selected.slot}"
                    f"{f' ({selected.label})' if selected.label else ''}; {hint.note}"
                )
            else:
                matches = rank_references(hd_slot, auto_references)
                best = matches[0]
                margin = confidence_margin(matches)
                hd_stage = c_string(hd_slot, 0x058, 8)
                if best.stage != hd_stage:
                    raise ValueError(
                        f"No exact-stage automatic GC reference for TPHD slot {hd_index} stage {hd_stage!r}; "
                        f"best candidate is {best.stage!r} from {best.path} slot {best.slot}"
                    )
                if margin < auto_reference_min_margin:
                    raise ValueError(
                        f"Automatic GC reference is ambiguous for TPHD slot {hd_index}: "
                        f"best {best.path} slot {best.slot} score {best.total}, margin {margin} "
                        f"is below required {auto_reference_min_margin}"
                    )
                selected = next(
                    reference
                    for reference in auto_references
                    if str(reference.path) == best.path and reference.slot == best.slot
                )
                label = f" ({best.label})" if best.label else ""
                slot_reference_detail = (
                    f"automatically selected {best.path} slot {best.slot}{label}; score {best.total}, "
                    f"margin {margin}; used its complete coherent GC state and overlaid only "
                    "TPHD identity/basic stats"
                )
            slot_reference_body = selected.body
            slot_reference_coherent_scene = True
        template_offset = GC_QUEST_LOG_OFFSETS[hd_index]
        template_quest_log = template[template_offset : template_offset + GC_QUEST_LOG_SIZE]
        body, report = build_mapped_body(
            hd_slot,
            template_quest_log,
            hd_index,
            hd_index,
            profile,
            slot_reference_body,
            slot_reference_detail,
            slot_reference_coherent_scene,
        )
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
        choices=PROFILES,
        default="safe",
        help="Conversion depth. safe is the current load-tested default; balanced/progress preserve more state but need validation.",
    )
    parser.add_argument("--json-report", type=Path, help="Write the conversion report as JSON")
    parser.add_argument(
        "--gc-state-reference",
        type=Path,
        help="Paired GC GCI whose scene/progression state should be grafted onto the converted slot",
    )
    parser.add_argument(
        "--gc-state-reference-slot",
        type=int,
        choices=(0, 1, 2),
        default=0,
        help="Slot index to read from --gc-state-reference, default: 0",
    )
    parser.add_argument(
        "--auto-gc-state-reference-root",
        action="append",
        type=Path,
        help="Search this GCI file/directory for the best exact-stage scene reference; may be repeated",
    )
    parser.add_argument(
        "--auto-reference-min-margin",
        type=int,
        default=50,
        help="Minimum score gap between the best and second automatic reference (default: 50)",
    )
    parser.add_argument(
        "--auto-reference-hints",
        type=Path,
        help="Optional version-1 JSON manifest mapping exact TPHD hashes to curated GC references",
    )
    args = parser.parse_args()

    if args.template is None:
        raise SystemExit("No GCI template found. Pass --template /path/to/01-GZ2E-gczelda2.gci")
    if args.gc_state_reference is not None and args.auto_gc_state_reference_root is not None:
        raise SystemExit("Use either --gc-state-reference or --auto-gc-state-reference-root, not both")
    if args.auto_reference_hints is not None and args.auto_gc_state_reference_root is None:
        raise SystemExit("--auto-reference-hints requires --auto-gc-state-reference-root")
    if args.auto_reference_min_margin < 0:
        raise SystemExit("--auto-reference-min-margin must be non-negative")

    reports = convert_cemu_save(
        args.cemu_save,
        args.template,
        args.output,
        args.slots,
        args.profile,
        args.gc_state_reference,
        args.gc_state_reference_slot,
        args.auto_gc_state_reference_root,
        args.auto_reference_min_margin,
        args.auto_reference_hints,
    )
    print(f"Wrote {args.output} ({GC_GCI_SIZE:#x} bytes)")
    print_report(reports)

    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(report_to_json(reports) + "\n", encoding="utf-8")
        print(f"Wrote report {args.json_report}")


if __name__ == "__main__":
    main()
