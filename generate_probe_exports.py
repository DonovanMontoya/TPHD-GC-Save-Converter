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
ABILITY_REFERENCES = {
    "any_mdh": (Path("Twilight Princess Any% Savefiles NTSC/9 MDH-MDHCastle-Desert.gci"), 0),
    "100_lanayru_twilight": (Path("TP 100% Saves - NTSC-U 6.17.20/06 - Lakebed 2, Lanayru, Post Lanayru.gci"), 1),
    "100_post_mdh": (Path("TP 100% Saves - NTSC-U 6.17.20/09 - Post MDH, Iza skip, Lake Cave.gci"), 0),
    "100_gorge_arc": (GC_GORGE_ARC_REFERENCE, GC_GORGE_ARC_SLOT),
}
ABILITY_RANGES = {
    "status_a": [(0x000, 0x028)],
    "status_b": [(0x028, 0x040)],
    "item_state": [(0x09C, 0x100)],
    "collect_light": [(0x100, 0x11C)],
    "event_flags": [(0x7F0, 0x8F0)],
    "item_collect_light": [(0x09C, 0x11C)],
    "event_collect_light": [(0x100, 0x11C), (0x7F0, 0x8F0)],
    "ability_core": [(0x09C, 0x11C), (0x7F0, 0x8F0)],
    "status_ability_core": [(0x000, 0x040), (0x09C, 0x11C), (0x7F0, 0x8F0)],
}
SCENT_CHILDREN = 0xB4
SCENT_POE = 0xB2
EVENT_MIDNA_CHARGE_ATTACK = 0x0501
EVENT_MIDNA_RIDING = 0x0C10
EVENT_SHADOW_CRYSTAL = 0x0D04
EVENT_STARTED_MDH = 0x0C01
EVENT_POST_MDH = 0x1E08
EVENT_CHILDREN_SCENT_CUTSCENE = 0x2240
EVENT_GAIN_SENSE = 0x4308
SCENT_PROBES = (
    "ability_flags_sense",
    "ability_flags_midna_charge",
    "ability_flags_midna_ride",
    "ability_flags_midna_charge_ride",
    "ability_flags_midna_charge_ride_shadow",
    "ability_flags_sense_and_charge",
    "ability_flags_mdh",
    "scent_children_select_slot",
    "scent_children_full",
    "scent_poe_from_gorge",
    "scent_sense_charge_children",
    "scent_sense_midna_multi_children",
)


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


def build_wolf_ability_probe(hd: bytes, template: bytes, slot: int, name: str) -> bytes:
    out = bytearray(template)
    offset = GC_QUEST_LOG_OFFSETS[slot]
    body = bytearray(template[offset : offset + GC_QUEST_LOG_BODY_SIZE])

    for rule_name in PROGRESS_RULES:
        apply_rule(body, hd, rule_name)

    scene_ref = reference_body(GC_ANY_FSP121_REFERENCE, GC_ANY_FSP121_SLOT)
    body[0x040:0x09C] = scene_ref[0x040:0x09C]

    prefix = "wolf_ability_"
    if not name.startswith(prefix):
        raise ValueError(f"unknown wolf ability probe {name}")
    suffix = name[len(prefix):]
    ref_name = next(
        (candidate for candidate in sorted(ABILITY_REFERENCES, key=len, reverse=True) if suffix.startswith(candidate + "_")),
        None,
    )
    if ref_name is None:
        raise ValueError(f"unknown ability reference in {name}")
    range_name = suffix[len(ref_name) + 1:]
    if range_name not in ABILITY_RANGES:
        raise ValueError(f"unknown ability range {range_name}")

    ref_path, ref_slot = ABILITY_REFERENCES[ref_name]
    ability_ref = reference_body(ref_path, ref_slot)
    for start, end in ABILITY_RANGES[range_name]:
        body[start:end] = ability_ref[start:end]

    patch_slot(out, bytes(body), slot)
    return bytes(out)


def set_event_bit(body: bytearray, event_flag: int) -> None:
    body[0x7F0 + (event_flag >> 8)] |= event_flag & 0xFF


def set_item_first_bit(body: bytearray, item_id: int) -> None:
    word_offset = 0x0CC + (item_id // 32) * 4
    bit = item_id % 32
    value = int.from_bytes(body[word_offset : word_offset + 4], "big")
    value |= 1 << bit
    body[word_offset : word_offset + 4] = value.to_bytes(4, "big")


def set_scent(body: bytearray, scent_item: int, *, select_slot_2: bool) -> None:
    body[0x016] = scent_item
    if select_slot_2:
        body[0x00D] = scent_item
    set_item_first_bit(body, scent_item)


def build_scent_ability_probe(hd: bytes, template: bytes, slot: int, name: str) -> bytes:
    out = bytearray(template)
    offset = GC_QUEST_LOG_OFFSETS[slot]
    body = bytearray(template[offset : offset + GC_QUEST_LOG_BODY_SIZE])

    for rule_name in PROGRESS_RULES:
        apply_rule(body, hd, rule_name)

    scene_ref = reference_body(GC_ANY_FSP121_REFERENCE, GC_ANY_FSP121_SLOT)
    body[0x040:0x09C] = scene_ref[0x040:0x09C]

    if name == "ability_flags_sense":
        set_event_bit(body, EVENT_GAIN_SENSE)
    elif name == "ability_flags_midna_charge":
        set_event_bit(body, EVENT_MIDNA_CHARGE_ATTACK)
    elif name == "ability_flags_midna_ride":
        set_event_bit(body, EVENT_MIDNA_RIDING)
    elif name == "ability_flags_midna_charge_ride":
        set_event_bit(body, EVENT_MIDNA_CHARGE_ATTACK)
        set_event_bit(body, EVENT_MIDNA_RIDING)
    elif name == "ability_flags_midna_charge_ride_shadow":
        set_event_bit(body, EVENT_MIDNA_CHARGE_ATTACK)
        set_event_bit(body, EVENT_MIDNA_RIDING)
        set_event_bit(body, EVENT_SHADOW_CRYSTAL)
        body[0x030] |= 0x08
    elif name == "ability_flags_sense_and_charge":
        set_event_bit(body, EVENT_GAIN_SENSE)
        set_event_bit(body, EVENT_MIDNA_CHARGE_ATTACK)
    elif name == "ability_flags_mdh":
        set_event_bit(body, EVENT_STARTED_MDH)
        set_event_bit(body, EVENT_POST_MDH)
    elif name == "scent_children_select_slot":
        body[0x00D] = body[0x016]
    elif name == "scent_children_full":
        set_scent(body, SCENT_CHILDREN, select_slot_2=True)
        set_event_bit(body, EVENT_CHILDREN_SCENT_CUTSCENE)
    elif name == "scent_poe_from_gorge":
        set_scent(body, SCENT_POE, select_slot_2=True)
        set_event_bit(body, EVENT_GAIN_SENSE)
    elif name == "scent_sense_charge_children":
        set_scent(body, SCENT_CHILDREN, select_slot_2=True)
        set_event_bit(body, EVENT_CHILDREN_SCENT_CUTSCENE)
        set_event_bit(body, EVENT_GAIN_SENSE)
        set_event_bit(body, EVENT_MIDNA_CHARGE_ATTACK)
    elif name == "scent_sense_midna_multi_children":
        set_scent(body, SCENT_CHILDREN, select_slot_2=True)
        set_event_bit(body, EVENT_CHILDREN_SCENT_CUTSCENE)
        set_event_bit(body, EVENT_GAIN_SENSE)
        set_event_bit(body, EVENT_MIDNA_CHARGE_ATTACK)
        set_event_bit(body, EVENT_MIDNA_RIDING)
    else:
        raise ValueError(f"unknown scent ability probe {name}")

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

    for ref_name in ABILITY_REFERENCES:
        for range_name in ABILITY_RANGES:
            probe_name = f"wolf_ability_{ref_name}_{range_name}"
            gci = build_wolf_ability_probe(hd, template, 0, probe_name)
            path = out_dir / f"probe-{probe_name}.gci"
            path.write_bytes(gci)
            if len(gci) != GC_GCI_SIZE:
                raise RuntimeError(f"wrong GCI size for {path}")
            print(path)

    for probe_name in SCENT_PROBES:
        gci = build_scent_ability_probe(hd, template, 0, probe_name)
        path = out_dir / f"probe-{probe_name}.gci"
        path.write_bytes(gci)
        if len(gci) != GC_GCI_SIZE:
            raise RuntimeError(f"wrong GCI size for {path}")
        print(path)


if __name__ == "__main__":
    main()
