"""Explicit save-format schemas for Twilight Princess conversion work.

The GC schema is sourced from the TP decomp `dSv_save_c` layout. The TPHD
schema is observed from `ZTP00.dat` samples and must be expanded with more
paired saves before fields are considered fully verified.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldDef:
    name: str
    offset: int
    size: int
    kind: str
    confidence: str
    note: str = ""


@dataclass(frozen=True)
class ConversionRule:
    name: str
    gc_offset: int
    size: int
    source_offset: int | None
    strategy: str
    confidence: str
    note: str = ""


GC_FIELDS: tuple[FieldDef, ...] = (
    FieldDef("player.status_a.max_life", 0x000, 2, "u16be", "known", "dSv_player_status_a_c.mMaxLife"),
    FieldDef("player.status_a.life", 0x002, 2, "u16be", "known", "dSv_player_status_a_c.mLife"),
    FieldDef("player.status_a.rupees", 0x004, 2, "u16be", "known", "dSv_player_status_a_c.mRupee"),
    FieldDef("player.status_a.max_oil", 0x006, 2, "u16be", "known", "dSv_player_status_a_c.mMaxOil"),
    FieldDef("player.status_a.oil", 0x008, 2, "u16be", "known", "dSv_player_status_a_c.mOil"),
    FieldDef("player.status_a.select_items", 0x00B, 4, "bytes", "known", "GC uses X/Y in first two slots; scent acquisition writes slot 2"),
    FieldDef("player.status_a.mix_items", 0x00F, 4, "bytes", "known"),
    FieldDef("player.status_a.equipment", 0x013, 6, "bytes", "known", "mSelectEquip[6]; index 3 is current scent"),
    FieldDef("player.status_a.wallet_size", 0x019, 1, "u8", "known"),
    FieldDef("player.status_a.magic", 0x01A, 4, "bytes", "known", "max magic, magic, magic flag, unknown"),
    FieldDef("player.status_a.transform_status", 0x01E, 1, "u8", "known"),
    FieldDef("player.status_b", 0x028, 0x18, "struct", "known"),
    FieldDef("player.horse_place", 0x040, 0x18, "struct", "known"),
    FieldDef("player.return_place", 0x058, 0x0C, "struct", "known", "stage[8], player status, room, unk10, unk11"),
    FieldDef("player.field_last_stay", 0x064, 0x1C, "struct", "known"),
    FieldDef("player.last_mark", 0x080, 0x1C, "struct", "known"),
    FieldDef("player.items", 0x09C, 0x30, "struct", "known", "24 item ids + 24 item slots"),
    FieldDef("player.get_item_flags", 0x0CC, 0x20, "u32be[8]", "known"),
    FieldDef("player.item_record", 0x0EC, 0x0C, "struct", "known", "arrows, bombs, bottles, slingshot"),
    FieldDef("player.item_max", 0x0F8, 0x08, "bytes", "known"),
    FieldDef("player.collect", 0x100, 0x10, "struct", "known", "collectibles/mirror/crystal/poe state; not current scent"),
    FieldDef("player.wolf", 0x110, 0x04, "struct", "known", "dSv_player_wolf_c unknown bytes; zero in current inspected references"),
    FieldDef("player.light_drop", 0x114, 0x08, "struct", "known"),
    FieldDef("player.letter_info", 0x11C, 0x50, "struct", "known"),
    FieldDef("player.fishing_info", 0x16C, 0x34, "struct", "known"),
    FieldDef("player.info.unknown0", 0x1A0, 0x08, "u64", "known"),
    FieldDef("player.info.total_time", 0x1A8, 0x08, "s64be", "known"),
    FieldDef("player.info.death_count", 0x1B2, 0x02, "u16be", "known"),
    FieldDef("player.info.player_name", 0x1B4, 0x10, "cstring", "known"),
    FieldDef("player.info.horse_name", 0x1C5, 0x10, "cstring", "known"),
    FieldDef("player.info.clear_count", 0x1D6, 0x01, "u8", "known"),
    FieldDef("player.config", 0x1E0, 0x0C, "struct", "known", "GC/Wii option semantics differ"),
    FieldDef("stage_memory", 0x1F0, 0x400, "dSv_memory_c[32]", "known"),
    FieldDef("visited_room_memory", 0x5F0, 0x200, "dSv_memory2_c[64]", "known"),
    FieldDef("event_flags", 0x7F0, 0x100, "bytes", "known", "dSv_event_c; flag 0xAABB maps to mEvent[0xAA] bit 0xBB"),
    FieldDef("reserve", 0x8F0, 0x50, "bytes", "known"),
    FieldDef("minigame_records", 0x940, 0x18, "struct", "known"),
    FieldDef("checksum", 0xA8C, 0x08, "u32be[2]", "known"),
)


TPHD_FIELDS: tuple[FieldDef, ...] = (
    FieldDef("hd.header_or_slot_flags", 0x000, 0x02, "bytes", "observed", "Not present in GC status_a; 0x0001 in every current valid sample"),
    FieldDef("player.status_a.max_life", 0x002, 2, "u16be", "observed", "Sample value 0x0017"),
    FieldDef("player.status_a.life", 0x004, 2, "u16be", "observed", "Sample value 0x000c"),
    FieldDef("player.status_a.rupees", 0x006, 2, "u16be", "observed", "Sample value 0x012b"),
    FieldDef("player.status_a.max_oil", 0x008, 2, "u16be", "observed", "0x5460 in every current valid sample"),
    FieldDef("player.status_a.oil", 0x00A, 2, "u16be", "observed", "Varies plausibly as lantern oil"),
    FieldDef("player.status_a.unknown10", 0x00C, 1, "u8", "observed", "Zero in every current valid sample; shifted equivalent of GC status_a unk10"),
    FieldDef("player.status_a.select_items", 0x00D, 4, "bytes", "observed", "Shifted +2 from GC layout; TPHD sample does not mirror scent into slot 2"),
    FieldDef("player.status_a.mix_items", 0x011, 4, "bytes", "observed", "Shifted +2 from GC layout"),
    FieldDef("player.status_a.equipment", 0x015, 6, "bytes", "observed", "Shifted +2 from GC layout; offset 0x018 is current scent candidate"),
    FieldDef("player.status_a.wallet_size", 0x01B, 1, "u8", "observed", "Values 0..3 across current samples"),
    FieldDef("player.status_a.magic", 0x01C, 4, "bytes", "observed", "Shifted +2 from GC layout; all zero in current samples"),
    FieldDef("player.status_a.transform_status", 0x020, 1, "u8", "observed", "Sample has 1 for wolf/current transform; most saves 0"),
    FieldDef("player.status_a.trailing_padding", 0x021, 0x07, "bytes", "sample_zero", "Zero in current samples"),
    FieldDef("player.status_b", 0x028, 0x18, "struct", "observed"),
    FieldDef("player.horse_place", 0x040, 0x18, "struct", "observed"),
    FieldDef("player.return_place", 0x058, 0x0C, "struct", "observed"),
    FieldDef("player.field_last_stay", 0x064, 0x1C, "struct", "observed"),
    FieldDef("player.last_mark", 0x080, 0x1C, "struct", "observed"),
    FieldDef("player.items", 0x09C, 0x30, "struct", "observed"),
    FieldDef("player.get_item_flags", 0x0CC, 0x20, "u32be[8]", "observed"),
    FieldDef("player.item_record", 0x0EC, 0x0C, "struct", "observed"),
    FieldDef("player.item_max", 0x0F8, 0x08, "bytes", "observed"),
    FieldDef("player.collect", 0x100, 0x10, "struct", "observed", "GC decomp says this is collectible state, not current scent"),
    FieldDef("player.wolf", 0x110, 0x04, "struct", "observed", "Probably not wolf ability unlocks; current sample is all zero"),
    FieldDef("player.light_drop", 0x114, 0x08, "struct", "observed"),
    FieldDef("player.letter_info", 0x11C, 0x50, "struct", "observed"),
    FieldDef("player.fishing_info", 0x16C, 0x34, "struct", "observed"),
    FieldDef("player.info.unknown0_or_padding", 0x1A0, 0x08, "bytes", "sample_zero", "Zero in current sample; GC has unknown0 here"),
    FieldDef("player.info.total_time", 0x1A8, 0x08, "s64be", "observed"),
    FieldDef("player.info.unknown1_or_padding", 0x1B0, 0x02, "bytes", "sample_zero", "Zero in current sample"),
    FieldDef("player.info.death_count", 0x1B2, 0x02, "u16be", "observed"),
    FieldDef("player.info.player_name", 0x1B4, 0x10, "cstring", "observed", "TPHD uses some following padding bytes for extra state"),
    FieldDef("player.info.after_player_name", 0x1C4, 0x01, "bytes", "sample_zero", "Zero in current sample"),
    FieldDef("player.info.horse_name", 0x1C5, 0x10, "cstring", "observed", "TPHD uses some following padding bytes for extra state"),
    FieldDef("player.info.after_horse_name", 0x1D5, 0x01, "bytes", "sample_zero", "Zero in current sample"),
    FieldDef("player.info.clear_count", 0x1D6, 0x01, "u8", "observed"),
    FieldDef("player.info.extra_or_padding", 0x1D7, 0x09, "bytes", "sample_zero", "Zero in current sample"),
    FieldDef("player.config_or_hd_options", 0x1E0, 0x10, "bytes", "observed_constant", "Same 16 bytes in all current samples; not byte-compatible with GC config"),
    FieldDef("stage_memory", 0x1F0, 0x400, "dSv_memory_c[32]", "structural", "Same size/position as GC; per-stage flag bits still need validation"),
    FieldDef("visited_room_memory", 0x5F0, 0x200, "dSv_memory2_c[64]", "structural", "Same size/position as GC; visited-room bit semantics still need validation"),
    FieldDef("event_flags", 0x7F0, 0x100, "bytes", "structural", "Same size/position as GC; event labels still need bit-level validation"),
    FieldDef("hd.current_stage_name", 0x8F0, 0x08, "cstring", "observed", "Not present in GC reserve"),
    FieldDef("hd.current_position_or_restart", 0x8F8, 0x18, "bytes", "observed", "Contains float-looking coordinates and packed room/spawn/layer bytes; needs controlled save validation"),
    FieldDef("hd.current_stage_padding", 0x910, 0x2E, "bytes", "sample_zero", "Zero in current sample"),
    FieldDef("hd.current_stage_flags_or_mode", 0x93E, 0x02, "bytes", "observed", "Nonzero in current sample; meaning unknown"),
    FieldDef("minigame_records", 0x940, 0x18, "struct", "observed"),
    FieldDef("post_save_padding", 0x958, 0x13C, "zero_padding", "observed", "Sample is zero; GC quest-log body has unused space after dSv_save_c"),
    FieldDef("hd_tail.zero_prefix", 0xA94, 0x05, "bytes", "sample_zero", "Zero in current samples; no GC destination"),
    FieldDef("hd_tail.late_game_block", 0xA99, 0x0C, "bytes", "hd_only", "Nonzero only in late-game Palace/Hyrule samples; no confirmed GC destination"),
    FieldDef("hd_tail.zero_mid", 0xAA5, 0x13, "bytes", "sample_zero", "Zero in current samples; no GC destination"),
    FieldDef("hd_tail.common_flag", 0xAB8, 0x01, "u8", "observed_constant", "0x01 in every current valid sample"),
    FieldDef("hd_tail.late_game_flags", 0xAB9, 0x03, "bytes", "hd_only", "Late-game flags; no confirmed GC destination"),
    FieldDef("hd_tail.zero_suffix", 0xABC, 0x33C, "bytes", "sample_zero", "Zero in current samples; no GC destination"),
    FieldDef("checksum", 0xDF8, 0x08, "u32be[2]", "known"),
)


CONVERSION_RULES: tuple[ConversionRule, ...] = (
    ConversionRule("player.status_a.max_life", 0x000, 2, 0x002, "copy", "observed"),
    ConversionRule("player.status_a.life", 0x002, 2, 0x004, "copy", "observed"),
    ConversionRule("player.status_a.rupees", 0x004, 2, 0x006, "copy", "observed"),
    ConversionRule("player.status_a.max_oil", 0x006, 2, 0x008, "copy", "observed", "Shifted +2 from GC status_a"),
    ConversionRule("player.status_a.oil", 0x008, 2, 0x00A, "copy", "observed", "Shifted +2 from GC status_a"),
    ConversionRule("player.status_a.unknown10", 0x00A, 1, 0x00C, "copy", "observed", "Shifted +2 from GC status_a"),
    ConversionRule("player.status_a.select_items", 0x00B, 4, 0x00D, "copy", "observed", "Shifted +2 from GC status_a"),
    ConversionRule("player.status_a.mix_items", 0x00F, 4, 0x011, "copy", "observed", "Shifted +2 from GC status_a"),
    ConversionRule("player.status_a.equipment", 0x013, 6, 0x015, "copy", "observed", "Shifted +2 from GC status_a"),
    ConversionRule("player.status_a.wallet_size", 0x019, 1, 0x01B, "copy", "observed", "Shifted +2 from GC status_a"),
    ConversionRule("player.status_a.magic", 0x01A, 4, 0x01C, "copy", "observed", "Shifted +2 from GC status_a"),
    ConversionRule("player.status_a.transform_status", 0x01E, 1, 0x020, "copy", "observed", "Shifted +2 from GC status_a"),
    ConversionRule("player.status_b", 0x028, 0x18, 0x028, "copy", "observed"),
    ConversionRule("player.horse_place", 0x040, 0x18, 0x040, "copy", "observed"),
    ConversionRule(
        "player.return_place",
        0x058,
        0x0C,
        0x058,
        "copy",
        "load_unsafe",
        "Direct-copy probe is visible in Dolphin but does not load; needs translation or paired location state",
    ),
    ConversionRule("player.field_last_stay", 0x064, 0x1C, 0x064, "copy", "observed"),
    ConversionRule("player.last_mark", 0x080, 0x1C, 0x080, "copy", "observed"),
    ConversionRule("player.items", 0x09C, 0x30, 0x09C, "copy", "observed"),
    ConversionRule("player.get_item_flags", 0x0CC, 0x20, 0x0CC, "copy", "observed"),
    ConversionRule("player.item_record", 0x0EC, 0x0C, 0x0EC, "copy", "observed"),
    ConversionRule("player.item_max", 0x0F8, 0x08, 0x0F8, "copy", "observed"),
    ConversionRule("player.collect", 0x100, 0x10, 0x100, "copy", "observed"),
    ConversionRule("player.wolf", 0x110, 0x04, 0x110, "copy", "observed"),
    ConversionRule("player.light_drop", 0x114, 0x08, 0x114, "copy", "observed"),
    ConversionRule("player.letter_info", 0x11C, 0x50, 0x11C, "copy", "observed"),
    ConversionRule("player.fishing_info", 0x16C, 0x34, 0x16C, "copy", "observed"),
    ConversionRule("player.info.total_time", 0x1A8, 0x08, 0x1A8, "copy", "observed"),
    ConversionRule("player.info.death_count", 0x1B2, 0x02, 0x1B2, "copy", "observed"),
    ConversionRule("player.info.player_name", 0x1B4, 0x10, 0x1B4, "cstring", "observed"),
    ConversionRule("player.info.horse_name", 0x1C5, 0x10, 0x1C5, "cstring", "observed"),
    ConversionRule("player.info.clear_count", 0x1D6, 0x01, 0x1D6, "copy", "observed"),
    ConversionRule("player.config", 0x1E0, 0x0C, None, "template", "unknown", "HD config/options differ"),
    ConversionRule("stage_memory", 0x1F0, 0x400, 0x1F0, "copy", "structural", "Same struct envelope as GC; requires bit-level validation"),
    ConversionRule("visited_room_memory", 0x5F0, 0x200, 0x5F0, "copy", "structural", "Same struct envelope as GC"),
    ConversionRule("event_flags", 0x7F0, 0x100, 0x7F0, "copy", "structural", "Requires event label compatibility check"),
    ConversionRule("reserve", 0x8F0, 0x50, None, "template", "unknown", "HD contents differ"),
    ConversionRule("minigame_records", 0x940, 0x18, 0x940, "copy", "observed"),
    ConversionRule("hd_extra_tail", 0xA94, 0x364, 0xA94, "drop", "unknown"),
)
