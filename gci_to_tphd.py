#!/usr/bin/env python3
"""Experimental GameCube/Dolphin GCI -> Twilight Princess HD slot converter.

The output starts from an existing 0xE00 TPHD ZTPxx.dat template so HD-only
configuration, current-runtime state, and tail bytes stay native. Only mapped
fields are overlaid from one checksum-valid GameCube quest log.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from save_schema import GC_TO_TPHD_RULES, ReverseConversionRule
from tphd_to_gci import (
    HD_QUEST_LOG_SIZE,
    PROFILES,
    FieldResult,
    SlotReport,
    checksum_pair,
    copy_c_string,
    c_string,
    quest_log_body_from_gci,
    read_u16be,
    validate_hd_slot,
)


def reverse_rule_enabled(rule: ReverseConversionRule, profile: str) -> bool:
    if rule.confidence in ("known", "observed"):
        return (
            profile in ("balanced", "progress")
            or rule.name.startswith("player.info.")
            or rule.name.startswith("player.status_a.")
        )
    return rule.confidence == "structural" and profile == "progress"


def build_tphd_slot(
    gc_body: bytes,
    hd_template: bytes,
    gc_slot: int,
    profile: str,
) -> tuple[bytes, SlotReport]:
    if profile not in PROFILES:
        raise ValueError(f"Unknown conversion profile {profile!r}")
    validate_hd_slot(hd_template, "TPHD template")
    if len(gc_body) != 0xA8C:
        raise ValueError(f"GC quest-log body must be 0xA8C bytes, got {len(gc_body):#x}")

    output = bytearray(hd_template)
    report = SlotReport(
        hd_slot=0,
        gc_slot=gc_slot,
        player_name=c_string(gc_body, 0x1B4, 16),
        horse_name=c_string(gc_body, 0x1C5, 16),
        max_life=read_u16be(gc_body, 0x000),
        current_life=read_u16be(gc_body, 0x002),
        rupees=read_u16be(gc_body, 0x004),
    )
    for rule in GC_TO_TPHD_RULES:
        if not reverse_rule_enabled(rule, profile):
            continue
        if rule.strategy == "copy":
            output[rule.hd_offset : rule.hd_offset + rule.size] = gc_body[
                rule.gc_offset : rule.gc_offset + rule.size
            ]
        elif rule.strategy == "cstring":
            copy_c_string(output, rule.hd_offset, gc_body, rule.gc_offset, rule.size)
        else:
            raise ValueError(f"Unsupported reverse strategy {rule.strategy!r}")
        report.fields.append(
            FieldResult(
                rule.name,
                rule.confidence,
                f"copied 0x{rule.size:x} bytes from GC 0x{rule.gc_offset:x} to HD 0x{rule.hd_offset:x}",
            )
        )

    total, negative = checksum_pair(output[:-8])
    output[-8:] = total.to_bytes(4, "big") + negative.to_bytes(4, "big")
    report.fields.extend(
        [
            FieldResult(
                "player.return_place",
                "template",
                "kept from TPHD template; cross-version location translation is not validated",
            ),
            FieldResult(
                "hd_only_state",
                "template",
                "kept TPHD options, runtime/current-stage block, padding, and HD-only tail from template",
            ),
            FieldResult(
                "reverse_status",
                "experimental",
                "checksum-valid structural conversion; Cemu/TPHD gameplay validation is still required",
            ),
        ]
    )
    converted = bytes(output)
    validate_hd_slot(converted, "converted TPHD slot")
    return converted, report


def convert_gci_to_tphd(
    gci_path: Path,
    hd_template_path: Path,
    output_path: Path,
    gc_slot: int,
    profile: str,
) -> SlotReport:
    body = quest_log_body_from_gci(gci_path.read_bytes(), gc_slot)
    converted, report = build_tphd_slot(body, hd_template_path.read_bytes(), gc_slot, profile)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(converted)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gci", type=Path, help="Twilight Princess GameCube .gci")
    parser.add_argument("hd_template", type=Path, help="Existing checksum-valid TPHD ZTPxx.dat template")
    parser.add_argument("output", type=Path, help="Output ZTPxx.dat path")
    parser.add_argument("--gc-slot", type=int, choices=(0, 1, 2), default=0)
    parser.add_argument("--profile", choices=PROFILES, default="safe")
    args = parser.parse_args()

    report = convert_gci_to_tphd(args.gci, args.hd_template, args.output, args.gc_slot, args.profile)
    print(f"Wrote {args.output} (0x{HD_QUEST_LOG_SIZE:x} bytes)")
    print(f"GC slot {report.gc_slot} -> TPHD slot file")
    print(f"Player: {report.player_name or '<blank>'}; rupees: {report.rupees}")
    print("WARNING: reverse conversion is experimental and has not yet been validated in Cemu/TPHD gameplay")


if __name__ == "__main__":
    main()
