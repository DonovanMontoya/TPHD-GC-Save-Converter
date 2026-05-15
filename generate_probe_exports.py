#!/usr/bin/env python3
"""Generate one-group-at-a-time TPHD -> GCI probe exports.

These files start from the proven safe mapping and add exactly one extra group
from the balanced/progress mappings. Use them to isolate which TPHD struct makes
the GameCube loader reject the converted save.
"""

from __future__ import annotations

from pathlib import Path

from save_schema import CONVERSION_RULES
from tphd_to_gci import (
    GC_GCI_SIZE,
    GC_QUEST_LOG_BODY_SIZE,
    GC_QUEST_LOG_OFFSETS,
    GC_QUEST_LOG_SIZE,
    checksum_pair,
    find_default_template,
    find_cemu_slots,
    parse_slot_index,
    validate_gci_template,
    validate_hd_slot,
)


GC_GORGE_ARC_REFERENCE = Path("TP 100% Saves - NTSC-U 6.17.20/11 - AG2, Post AG, Gorge Arc.gci")
GC_GORGE_ARC_SLOT = 2
GC_ANY_FSP121_REFERENCE = Path("Twilight Princess Any% Savefiles NTSC/4 EponaOOB-RupeeRoll-EldinVessel.gci")
GC_ANY_FSP121_SLOT = 1


SAFE_RULES = {
    "player.status_a.max_life",
    "player.status_a.life",
    "player.status_a.rupees",
    "player.status_a.max_oil",
    "player.status_a.oil",
    "player.status_a.unknown10",
    "player.status_a.select_items",
    "player.status_a.mix_items",
    "player.status_a.equipment",
    "player.status_a.wallet_size",
    "player.status_a.magic",
    "player.status_a.transform_status",
    "player.info.total_time",
    "player.info.death_count",
    "player.info.player_name",
    "player.info.horse_name",
    "player.info.clear_count",
}


PROBE_GROUPS = {
    "status_b": ["player.status_b"],
    "horse_place": ["player.horse_place"],
    "return_place": ["player.return_place"],
    "field_last_stay": ["player.field_last_stay"],
    "last_mark": ["player.last_mark"],
    "items": ["player.items"],
    "get_item_flags": ["player.get_item_flags"],
    "item_record": ["player.item_record"],
    "item_max": ["player.item_max"],
    "collect": ["player.collect"],
    "wolf": ["player.wolf"],
    "light_drop": ["player.light_drop"],
    "letter_info": ["player.letter_info"],
    "fishing_info": ["player.fishing_info"],
    "minigame_records": ["minigame_records"],
    "stage_memory": ["stage_memory"],
    "visited_room_memory": ["visited_room_memory"],
    "event_flags": ["event_flags"],
    "cleared_status_items_flags": ["player.status_b", "player.items", "player.get_item_flags"],
}


PROGRESS_RULES = [
    rule.name
    for rule in CONVERSION_RULES
    if rule.confidence in ("observed", "structural") and rule.source_offset is not None
]


def copy_c_string(dst: bytearray, dst_offset: int, src: bytes, src_offset: int, size: int) -> None:
    dst[dst_offset : dst_offset + size] = b"\x00" * size
    raw = src[src_offset : src_offset + size]
    end = raw.find(b"\x00")
    if end == -1:
        end = size
    dst[dst_offset : dst_offset + end] = raw[:end]


def apply_rule(body: bytearray, hd: bytes, name: str) -> None:
    rule = next(rule for rule in CONVERSION_RULES if rule.name == name)
    if rule.source_offset is None:
        return
    if rule.strategy == "copy":
        body[rule.gc_offset : rule.gc_offset + rule.size] = hd[
            rule.source_offset : rule.source_offset + rule.size
        ]
    elif rule.strategy == "cstring":
        copy_c_string(body, rule.gc_offset, hd, rule.source_offset, rule.size)
    else:
        raise ValueError(f"unsupported strategy {rule.strategy}")


def patch_slot(out: bytearray, body: bytes, slot: int) -> None:
    offset = GC_QUEST_LOG_OFFSETS[slot]
    out[offset : offset + GC_QUEST_LOG_BODY_SIZE] = body
    csum, nsum = checksum_pair(body)
    out[offset + GC_QUEST_LOG_BODY_SIZE : offset + GC_QUEST_LOG_SIZE] = (
        csum.to_bytes(4, "big") + nsum.to_bytes(4, "big")
    )


def build_probe(hd: bytes, template: bytes, slot: int, extra_rules: list[str]) -> bytes:
    out = bytearray(template)
    offset = GC_QUEST_LOG_OFFSETS[slot]
    body = bytearray(template[offset : offset + GC_QUEST_LOG_BODY_SIZE])

    for name in SAFE_RULES:
        apply_rule(body, hd, name)
    for name in extra_rules:
        apply_rule(body, hd, name)

    patch_slot(out, bytes(body), slot)
    return bytes(out)


def build_custom_probe(hd: bytes, template: bytes, slot: int, name: str) -> bytes:
    out = bytearray(template)
    offset = GC_QUEST_LOG_OFFSETS[slot]
    body = bytearray(template[offset : offset + GC_QUEST_LOG_BODY_SIZE])

    for rule_name in PROGRESS_RULES:
        apply_rule(body, hd, rule_name)

    if name == "scene_progress_return_place":
        apply_rule(body, hd, "player.return_place")
    elif name == "scene_progress_return_stage_only":
        body[0x058:0x060] = hd[0x058:0x060]
    elif name == "scene_progress_current_reserve":
        body[0x8F0:0x940] = hd[0x8F0:0x940]
    elif name == "scene_progress_return_and_current":
        apply_rule(body, hd, "player.return_place")
        body[0x8F0:0x940] = hd[0x8F0:0x940]
    elif name == "scene_progress_stage_only_and_current":
        body[0x058:0x060] = hd[0x058:0x060]
        body[0x8F0:0x940] = hd[0x8F0:0x940]
    else:
        raise ValueError(f"unknown custom probe {name}")

    patch_slot(out, bytes(body), slot)
    return bytes(out)


def reference_body(path: Path, slot: int) -> bytes:
    data = path.read_bytes()
    offset = GC_QUEST_LOG_OFFSETS[slot]
    return data[offset : offset + GC_QUEST_LOG_BODY_SIZE]


def build_reference_scene_probe(hd: bytes, template: bytes, slot: int, name: str) -> bytes:
    out = bytearray(template)
    offset = GC_QUEST_LOG_OFFSETS[slot]
    body = bytearray(template[offset : offset + GC_QUEST_LOG_BODY_SIZE])

    for rule_name in PROGRESS_RULES:
        apply_rule(body, hd, rule_name)

    if name.startswith("scene_progress_gc_gorge_arc"):
        ref = reference_body(GC_GORGE_ARC_REFERENCE, GC_GORGE_ARC_SLOT)
    elif name.startswith("scene_progress_gc_any_fsp121"):
        ref = reference_body(GC_ANY_FSP121_REFERENCE, GC_ANY_FSP121_SLOT)
    else:
        raise ValueError(f"unknown reference scene probe {name}")

    if name.endswith("_return_only"):
        body[0x058:0x064] = ref[0x058:0x064]
    elif name.endswith("_location_bundle"):
        body[0x040:0x09C] = ref[0x040:0x09C]
    elif name.endswith("_runtime_location_bundle"):
        body[0x028:0x09C] = ref[0x028:0x09C]
    else:
        raise ValueError(f"unknown reference scene probe {name}")

    patch_slot(out, bytes(body), slot)
    return bytes(out)


def main() -> None:
    template_path = find_default_template()
    if template_path is None:
        raise SystemExit("No default GCI template found")
    template = template_path.read_bytes()
    validate_gci_template(template)

    slot_path = next(path for path in find_cemu_slots(Path("CemuSave")) if parse_slot_index(path) == 0)
    hd = slot_path.read_bytes()
    validate_hd_slot(hd, str(slot_path))

    out_dir = Path("probe-exports")
    out_dir.mkdir(exist_ok=True)

    for group_name, rules in PROBE_GROUPS.items():
        gci = build_probe(hd, template, 0, rules)
        path = out_dir / f"probe-{group_name}.gci"
        path.write_bytes(gci)
        if len(gci) != GC_GCI_SIZE:
            raise RuntimeError(f"wrong GCI size for {path}")
        print(path)

    for probe_name in (
        "scene_progress_return_place",
        "scene_progress_return_stage_only",
        "scene_progress_current_reserve",
        "scene_progress_return_and_current",
        "scene_progress_stage_only_and_current",
    ):
        gci = build_custom_probe(hd, template, 0, probe_name)
        path = out_dir / f"probe-{probe_name}.gci"
        path.write_bytes(gci)
        if len(gci) != GC_GCI_SIZE:
            raise RuntimeError(f"wrong GCI size for {path}")
        print(path)

    for probe_name in (
        "scene_progress_gc_gorge_arc_return_only",
        "scene_progress_gc_gorge_arc_location_bundle",
        "scene_progress_gc_gorge_arc_runtime_location_bundle",
        "scene_progress_gc_any_fsp121_return_only",
        "scene_progress_gc_any_fsp121_location_bundle",
        "scene_progress_gc_any_fsp121_runtime_location_bundle",
    ):
        gci = build_reference_scene_probe(hd, template, 0, probe_name)
        path = out_dir / f"probe-{probe_name}.gci"
        path.write_bytes(gci)
        if len(gci) != GC_GCI_SIZE:
            raise RuntimeError(f"wrong GCI size for {path}")
        print(path)


if __name__ == "__main__":
    main()
