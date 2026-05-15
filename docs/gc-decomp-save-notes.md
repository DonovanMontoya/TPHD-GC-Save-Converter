# GC Decomp Save Notes

These notes mine facts from the local GameCube decomp at
`/Users/donovan/Documents/Github/tp`. They are reference facts for the
converter; the decomp itself is not copied into this repository.

## Quest Log Layout

`include/d/d_save.h` defines `dSv_save_c` as `0x958` bytes. In the Dolphin GCI
quest-log body this sits before the checksum:

| Offset | Size | Decomp type |
| --- | ---: | --- |
| `0x000` | `0x1EC` | `dSv_player_c mPlayer` |
| `0x1F0` | `0x400` | `dSv_memory_c mSave[32]` |
| `0x5F0` | `0x200` | `dSv_memory2_c mSave2[64]` |
| `0x7F0` | `0x100` | `dSv_event_c mEvent` |
| `0x8F0` | `0x050` | reserve |
| `0x940` | `0x018` | minigame records |

The `dSv_event_c` bit packing is explicit in `src/d/d_save.cpp`: a flag value
`0xAABB` maps to `mEvent[0xAA] |= 0xBB`. This gives us direct event-byte
addresses for probe work.

## Player State

`dSv_player_status_a_c` starts at GC body `0x000` and is `0x28` bytes:

| GC offset | Field |
| ---: | --- |
| `0x000` | max life |
| `0x002` | current life |
| `0x004` | rupees |
| `0x006` | max oil |
| `0x008` | oil |
| `0x00B` | selected item slots |
| `0x00F` | mixed item slots |
| `0x013` | selected equipment |
| `0x019` | wallet size |
| `0x01A` | magic block |
| `0x01E` | transform status |

`dComIfGs_getCollectSmell()` is named misleadingly for save mapping. It reads
`mSelectEquip[COLLECT_SMELL]`, where `COLLECT_SMELL = 3`. Therefore current
scent is stored at GC body `0x013 + 3 = 0x016`. In TPHD, the status block is
shifted by two bytes, so the corresponding source candidate is `0x018`.

When the game grants a scent, `dMsgObject_c::setSmellTypeLocal()` does three
things:

- turns on the item-first bit for the scent item
- writes the scent item into selected equipment index 3
- writes the scent item into selected item slot 2

The scent item IDs from `include/d/d_item_data.h` are:

| Item | ID |
| --- | ---: |
| Ilia pouch scent | `0xB0` |
| Poe scent | `0xB2` |
| Fish scent | `0xB3` |
| Children scent | `0xB4` |
| Medicine scent | `0xB5` |

## Event Flags

The decomp gives exact candidates for the reported missing wolf abilities:

| Flag | Value | Meaning |
| --- | ---: | --- |
| `M_015` | `0x0501` | Can use Midna's B charge attack |
| `F_0250` | `0x1E08` | Midna revived / completed Midna's Desperate Hour |
| `F_0279` | `0x2240` | Saw cutscene about scent of kids from wooden sword |
| `F_0280` | `0x2220` | Saw cutscene about Ilia's scent from pouch |
| `F_0550` | `0x4308` | Gain ability to use sense |

`daAlink_c::checkWolfUseAbility()` checks `F_0550` before toggling wolf sense.
`daAlink_c::checkMidnaChargeAttack()` checks event bit `0x0501`.

The current TPHD sample has a children scent value at source offset `0x018`, but
its copied event flag block does not set `F_0550` or `M_015`. That explains why
a converted save can load while still missing sense and the wolf multi-enemy
attack.
