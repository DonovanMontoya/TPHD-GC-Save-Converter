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

1. Wolf ability focused probes: `wolf`, `collect`, `status_b`, and event/flag combinations.
2. A reference comparison between working Any% `F_SP121` bundle and TPHD wolf ability flags.
3. Avoid `Gorge Arc` location bundles for this source save unless more paired state is translated.

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

The latest scene probes show that a load-safe `F_SP121` return context is
possible, but it does not restore wolf sense/scent or the multi-enemy wolf
attack. Those are now separate ability/state flags rather than scene-loader
fields.
