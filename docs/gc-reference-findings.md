# GameCube Reference Findings

The GC reference set currently includes:

- `Twilight Princess Any% Savefiles NTSC`: 15 GCI files, 45 valid quest-log slots.
- `TP 100% Saves - NTSC-U 6.17.20`: 20 GCI files, 60 valid quest-log slots.

All 105 parsed quest-log slots have valid GC save checksums and game id `GZ2E01`.

## Why These Matter

The reference saves give us target-side examples for valid GC values and struct
patterns. They do not prove that every unseen value is invalid, but they help
separate simple value novelty from data that is probably HD-specific or
mis-mapped.

`exported-schema-safe.gci` loads, so the known-good baseline is:

- GCI wrapper and quest-log checksum generation.
- Shifted TPHD `status_a` mapping.
- C-string copying for player and horse names.
- Keeping GC config/reserve data from the template.

`exported-schema-balanced.gci` fails, which means at least one additional
observed group is not directly GC-load-safe. Probe testing has now confirmed
that `player.return_place` is one such group.

## Current Audit

Generated with:

```bash
python3 audit_gc_reference_ranges.py \
  CemuSave/1019e500/user/80000001/ZTP00.dat \
  docs/gc-reference-audit-slot0.csv \
  "Twilight Princess Any% Savefiles NTSC" \
  "TP 100% Saves - NTSC-U 6.17.20"
```

The audit compares each mapped TPHD group against all 105 GC reference slots.
It reports exact matches, nearest byte distance, and positions where the TPHD
source byte has not appeared in any GC reference at that same offset.

Important interpretation:

- A mismatch in a `safe` field is not automatically fatal, because safe loads.
- Location structs, flag blocks, and inventory blocks are more suspicious than
  rupee/oil/name mismatches.
- The probe exports in `probe-exports/` remain the decisive Dolphin test for
  isolating the `balanced` failure.

## Current Suspects

Current probe results:

| Probe | Result | Interpretation |
| --- | --- | --- |
| `probe-return_place.gci` | fails | direct copy is unsafe despite matching one GC reference byte pattern |
| `probe-status_b.gci` | loads | individually load-safe |
| `probe-items.gci` | loads | individually load-safe |
| `probe-get_item_flags.gci` | loads | individually load-safe |
| `probe-cleared_status_items_flags.gci` | loads | cleared groups are load-safe together |
| `exported-balanced-minus-return.gci` | loads | all current balanced groups are load-safe once `return_place` is excluded |
| `exported-progress-minus-return.gci` | loads, without Midna | structural progress blocks are loader-safe; companion/current-scene state is still incomplete |
| `probe-stage_memory.gci` | loads | stage memory is individually load-safe |
| `probe-visited_room_memory.gci` | loads | visited-room memory is individually load-safe |
| `probe-event_flags.gci` | loads | event flags are individually load-safe |
| `probe-scene_progress_return_stage_only.gci` | full crash | changing GC return stage to `F_SP121` alone is unsafe |
| `probe-scene_progress_current_reserve.gci` | loads | TPHD current-stage/reserve block is loader-safe |
| `probe-scene_progress_stage_only_and_current.gci` | full crash | current-stage reserve does not make return-stage rewrite safe |
| `probe-scene_progress_return_place.gci` | fails to load | full TPHD return-place direct copy remains unsafe |
| `probe-scene_progress_return_and_current.gci` | fails to load | full return-place plus current-stage reserve remains unsafe |
| `probe-scene_progress_gc_gorge_arc_location_bundle.gci` | fails to load | exact-matching 100% `Gorge Arc` location bundle is not compatible with this converted progress state |
| `probe-scene_progress_gc_gorge_arc_runtime_location_bundle.gci` | fails to load | adding GC `status_b` does not make the `Gorge Arc` bundle compatible |
| `probe-scene_progress_gc_any_fsp121_location_bundle.gci` | loads, missing sense/scent and wolf multi-enemy attack | Any% `F_SP121` bundle is loader-compatible but still semantically incomplete |
| `probe-scene_progress_gc_any_fsp121_runtime_location_bundle.gci` | loads, missing sense/scent and wolf multi-enemy attack | copying matching GC `status_b` does not restore those wolf abilities |

Next highest-priority scene-state files to test:

1. `probe-wolf_ability_any_mdh_ability_core.gci`
2. `probe-wolf_ability_any_mdh_event_flags.gci`
3. `probe-wolf_ability_any_mdh_item_collect_light.gci`
4. `probe-wolf_ability_100_post_mdh_ability_core.gci`
5. `probe-wolf_ability_100_post_mdh_event_flags.gci`
6. `probe-wolf_ability_100_lanayru_twilight_ability_core.gci`
7. Avoid `Gorge Arc` location bundles for this source save unless more paired state is translated.

## Semantic Gaps

The current progress export still keeps GC template `return_place` and reserve
bytes because direct-copying TPHD `player.return_place` fails to load. For the
current sample, TPHD wants `F_SP121` in both return/current-stage state, while
the generated GC file keeps the template return stage `F_SP103` and a zeroed
GC reserve block. That explains why the file can load but still miss scene
context such as Midna.

The next converter problem is not checksum or loader compatibility; it is
translating current/return scene state safely enough to restore companion and
spawn context.

The scene-state probes all start from the load-tested progress baseline:

- `return_stage_only`: copies only the 8-byte TPHD return-stage name into GC
  `return_place`.
- `current_reserve`: copies TPHD `0x8F0..0x93F` into GC reserve.
- `stage_only_and_current`: combines those two lower-risk changes.
- `return_place`: copies the full 12-byte TPHD return-place struct on top of
  progress.
- `return_and_current`: combines full return-place with TPHD current-stage
  reserve bytes.

The TPHD sample's full return-place bytes exactly match the 100% `Gorge Arc`
GC reference slot, so the newest probes try grafting coherent GC-side location
bundles around valid `F_SP121` return state:

- `gc_gorge_arc_*`: uses the exact matching 100% `Gorge Arc` reference.
- `gc_any_fsp121_*`: uses an Any% `F_SP121` reference with a coherent
  Faron/Eldin bridge location bundle.
- `location_bundle`: copies GC `horse_place` through `last_mark`.
- `runtime_location_bundle`: also copies GC `status_b`.
- `return_only`: copies only the 12-byte Any% `F_SP121` return-place tuple.

The latest scene probes show that a load-safe `F_SP121` return context is
possible, but only when it is grafted from a coherent GC reference bundle. A
direct TPHD location translation is still not known.

Current location-specific conclusions:

- GC game start uses `player.return_place.stage`, `player.return_place.playerStatus`,
  and `player.return_place.roomNo` directly.
- Direct TPHD `player.return_place` is unsafe.
- Writing only the TPHD return stage `F_SP121` is worse: it fully crashes.
- Copying the TPHD current-stage reserve block loads, but does not make
  `return_place` safe.
- A known-good Any% GC `F_SP121` bundle loads in this converted progress state.
- The Any% GC `F_SP121` return-only tuple loads too, but it is semantically too
  early for the current TPHD sample: the game asks for bridge repair while warp
  points are not unlocked.
- The 100% `Gorge Arc` bundle does not load, even though its 12-byte
  `return_place` exactly matches the current TPHD sample.

That last point is the important blocker: location conversion needs a coherent
stage/room/start/layer/progress translation. It cannot be promoted to the
converter as direct copying of `return_place`, and it should not be inferred
from stage name alone.

## Wolf Ability Probes

The wolf ability probes all start from the load-tested progress baseline plus
the Any% `F_SP121` location bundle that loads. They then graft specific
ability-relevant GC byte ranges from known wolf/Midna references.

Reference prefixes:

- `any_mdh`: Any% `Midna's Desperate Hour`.
- `100_lanayru_twilight`: 100% `Lanayru Twilight`.
- `100_post_mdh`: 100% `Post Midna's Desperate Hour`.
- `100_gorge_arc`: 100% `Gorge Arc`.

Range suffixes:

- `status_a`: `0x000..0x027`, including current transform/equipment basics.
- `status_b`: `0x028..0x03F`, runtime/player status.
- `item_state`: `0x09C..0x0FF`, item inventory/get-item/ammo state.
- `collect_light`: `0x100..0x11B`, collect/wolf/light-drop state.
- `event_flags`: `0x7F0..0x8EF`.
- `ability_core`: `item_state + collect_light + event_flags`.
- `status_ability_core`: `status_a + status_b + ability_core`.

The broad wolf ability graft probes are now secondary because targeted
decomp-backed probes identified the needed scent/sense/Midna flags.

## Confirmed Wolf Ability Fix

The targeted decomp-based probes for ability flags and scent state load and
restore scent/sense and Midna multi-target attack behavior on the current
sample. The important GC facts are:

- current scent is `status_a.equipment[3]` at body offset `0x016`;
- scent acquisition also needs the scent item-first bit and selected item slot
  2;
- wolf sense is event flag `F_0550 = 0x4308`;
- Midna's B charge attack is event flag `M_015 = 0x0501`;
- Midna's multi-target attack additionally needs `M_067 = 0x0C10`, which gates
  `checkMidnaRide()`.

The converter now applies this as derived normalization for `balanced` and
`progress` profiles when TPHD source offset `0x018` contains a known scent item.
`probe-ability_flags_midna_charge_ride.gci` confirms that the `0x0501 + 0x0C10`
pair is sufficient for the Midna multi-target attack in the current sample.

## Next Location Probes

The next useful location probes should start from the load-tested progress save
with the confirmed wolf ability normalization, then use the Any% `F_SP121`
bundle as the known-loading location baseline. Test one change at a time:

Generated files:

1. `probe-scene_progress_any_fsp121_return_player_status_from_hd.gci`
2. `probe-scene_progress_any_fsp121_return_room_from_hd.gci`
3. `probe-scene_progress_any_fsp121_field_last_stay_from_hd.gci`
4. `probe-scene_progress_any_fsp121_horse_place_from_hd.gci`
5. `probe-scene_progress_any_fsp121_current_reserve_from_hd.gci`
6. Search for the minimum event/stage-memory bits that make the 100% `Gorge Arc`
   tuple load.

These probes now start from the converter's real `progress` body, including the
derived wolf scent/sense/Midna normalization, before grafting the known-loading
Any% `F_SP121` location bundle. The first two probes differ from that baseline
by exactly one quest-log body byte, excluding checksum.

Follow-up bridge/portal probes generated after the Any% `return_only` result:

1. `probe-scene_progress_gc_any_fsp121_return_only_portal_core_flags.gci`
2. `probe-scene_progress_gc_any_fsp121_return_only_kakariko_bridge_restored_flag.gci`
3. `probe-scene_progress_gc_any_fsp121_return_only_eldin_bridge_disappears_flag.gci`
4. `probe-scene_progress_gc_any_fsp121_return_only_eldin_bridge_warped_flag.gci`
5. `probe-scene_progress_gc_any_fsp121_return_only_gorge_bridge_flags.gci`
6. `probe-scene_progress_gc_any_fsp121_return_only_gorge_event_prefix.gci`
7. `probe-scene_progress_gc_any_fsp121_return_only_gorge_stage_memory.gci`
8. `probe-scene_progress_gc_any_fsp121_return_only_gorge_stage_memory_and_bridge_flags.gci`

Decomp reason for these probes:

- `dMenu_Fmap2DTop_c::isWarpAccept()` requires `M_021 = 0x0604` for normal
  portal warp access.
- Portal icons require stage switches through `checkDrawPortalIcon()`, so event
  bits alone may unlock the warp mode without showing destinations.
- Bridge-related map text checks `M_018 = 0x0620` for Kakariko bridge restored
  and `M_092 = 0x0F08` for Eldin bridge warped.
- Test result: `probe-scene_progress_gc_any_fsp121_return_only_portal_core_flags.gci`
  loads and works as intended, and it also adds the transform option because it
  includes `M_077 = 0x0D04` (`Get shadow crystal`).
- Test result: the short-list `03-bridge-flags.gci` and `04-portal-icons.gci`
  work as intended in the current Dolphin pass.
- Test result: `05-current-best.gci` works as intended as a combined probe, but
  it grants transform/bridge/warp state not proven to exist in the TPHD source.
  It is intentionally not part of the normal converter.

Use `inspect_gci_state.py` before Dolphin testing. It reports the relevant
return tuple, event bits, and stage-switch words for a generated GCI and can
diff those gates against reference saves. The validation loop should now be:
decomp gate -> inspector diff -> one targeted Dolphin observation.

## Paired Wooden-Sword-Scent Reference

`GameCubeSave/the-legend-of-zelda-twilight-princess.33971.gci` slot 0 is a
local GC save at the same story point as the TPHD source: it has children scent
`0xB4`, `F_SP121` return-place `point=1 room=2`, `M_077` off, and the right
early portal/Forest Temple event state (`M_014` and `M_022` on, but first
portal warp and bridge repair flags off).

The converter now supports an explicit `--gc-state-reference` option for this
case. It copies only scene/progression state from the paired GC save:
`return_place`, `stage_memory`, and `event_flags`. Mapped TPHD stats and
inventory are still applied separately, and wolf scent/sense/Midna ability
normalization is applied afterward.

Generated output:

```bash
python3 tphd_to_gci.py CemuSave \
  artifacts/exports/exported-progress-paired-wood-scent.gci \
  --profile progress \
  --gc-state-reference "GameCubeSave/the-legend-of-zelda-twilight-princess.33971.gci" \
  --gc-state-reference-slot 0 \
  --json-report artifacts/reports/exported-progress-paired-wood-scent-report.json
```

`inspect_gci_state.py` reports no scene/event/stage-switch differences between
that generated output and the GC reference; only normal TPHD-mapped stats such
as life and rupees differ.

## Forward location-struct evidence review (2026-08-14)

`player.horse_place`, `player.field_last_stay`, and `player.last_mark` were
carried at `observed` confidence from the initial mapping commit. A review of
the tracked evidence found no controlled paired-save diff and no focused Dolphin
observation for any of the three in the forward direction:

- `docs/save-format-map.md` defines `observed` as "named from the sample and/or
  has a clear GC analogue" — structural plausibility, which `AGENTS.md` does not
  treat as promotable on its own.
- The `exported-balanced-minus-return.gci` result records only that the save
  loads, which `AGENTS.md` discounts as loader compatibility.
- `probe-scene_progress_any_fsp121_field_last_stay_from_hd.gci` and
  `probe-scene_progress_any_fsp121_horse_place_from_hd.gci` were generated to
  settle exactly this question and were never run.
- Every Dolphin result that exercises a full corpus uses the automatic
  coherent-scene path or the `safe` profile, neither of which applies these
  rules, so none of those runs speak to them.

The structs are also not independent. In the GC decomp, `field_last_stay`
carries region-discovery bits set in lockstep with visited-room memory and read
by the world map, and `last_mark` supplies the Midna warp destination and its
accept flag. Because `player.return_place` was already excluded, `balanced` and
`progress` emitted a bundle assembled from two saves at once. Measured on the
pinned paired export, the output combined a TPHD `field_last_stay` of `F_SP108`
with a GC `return_place` of `F_SP121`, and blanked the reference's `D_MN05` warp
mark.

Forward conversion now excludes the whole bundle, matching the reverse
direction. Live re-validation is tracked in `docs/dolphin-test-log.md`.

### Open question: widening the explicit reference graft

`apply_gc_state_reference` still grafts only `0x058..0x064`, so an explicit
reference supplies `return_place` while the other three come from the GC
template — one GC save mixed with another, rather than TPHD mixed with GC.
Widening the graft to `0x040..0x09C` would take the whole bundle from a single
coherent reference. The only evidence today is that
`probe-scene_progress_gc_any_fsp121_location_bundle.gci` loads, which is not
sufficient to promote a wider graft. Settling it needs a focused Dolphin run
comparing the widened output against the reference's own scene state.
