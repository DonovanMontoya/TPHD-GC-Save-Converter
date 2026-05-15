# TPHD to Dolphin GCI Converter

`tphd_to_gci.py` converts a Twilight Princess HD Cemu save folder into a
GameCube/Dolphin `.gci` using an existing Twilight Princess GameCube save as
the GCI metadata template.

TPHD is not byte-compatible with the GameCube save format. The converter uses
profiles so unknown HD-only state is not silently copied into GC-only fields.

## Usage

```bash
python3 tphd_to_gci.py CemuSave exported-safe.gci
```

The script auto-discovers `ZTP00.dat`, `ZTP01.dat`, and `ZTP02.dat` under the
Cemu save folder and writes the matching GC quest-log slots.

If the template is not in `GameCubeSave/Card A/01-GZ2E-gczelda2.gci`, pass it:

```bash
python3 tphd_to_gci.py CemuSave exported-balanced.gci \
  --template "/path/to/01-GZ2E-gczelda2.gci"
```

## Profiles

- `safe`: most likely to load. Copies player/horse names, health, rupees, play
  time, death count, and clear count. Most progression remains from the GC
  template.
- `balanced`: experimental. Adds inventory, item flags, item counts, location
  structs, collectibles, letters, fishing, and minigame records.
- `progress`: experimental. Adds stage memory, visited-room memory, and event
  flags. This preserves more progress but is the highest-risk profile until
  those flags are fully validated against TPHD.

```bash
python3 tphd_to_gci.py CemuSave exported-safe.gci --profile safe
python3 tphd_to_gci.py CemuSave exported-balanced.gci --profile balanced
python3 tphd_to_gci.py CemuSave exported-progress.gci --profile progress
```

## Test Order

Test in Dolphin in this order:

1. `exported-safe.gci`
2. `exported-balanced.gci`
3. `exported-progress.gci`

If `safe` loads, the GCI wrapper and basic remapping are sound. If `balanced`
or `progress` fails, the failed profile identifies which field group needs
deeper reverse engineering.

Current status: the schema-based safe export loads in Dolphin for the provided
sample save. The schema-based balanced and progress exports currently fail, so
do not treat those profiles as usable converter outputs yet.

## Current Mapping Aids

GC reference summaries:

```bash
python3 analyze_gc_collection.py "Twilight Princess Any% Savefiles NTSC" \
  docs/gc-anypercent-summary.csv
python3 analyze_gc_collection.py "TP 100% Saves - NTSC-U 6.17.20" \
  docs/gc-100percent-summary.csv
```

Compare one TPHD slot against all current GC references:

```bash
python3 audit_gc_reference_ranges.py \
  CemuSave/1019e500/user/80000001/ZTP00.dat \
  docs/gc-reference-audit-slot0.csv \
  "Twilight Princess Any% Savefiles NTSC" \
  "TP 100% Saves - NTSC-U 6.17.20"
```

One-group Dolphin probe exports are in `probe-exports/`. They start from the
known-loading safe profile and add exactly one extra group, which is the fastest
way to isolate why `balanced` fails.

Current probe results:

- `probe-return_place.gci`: fails, so `player.return_place` is skipped by
  normal profiles until it has a real translation.
- `probe-status_b.gci`: loads.
- `probe-items.gci`: loads.
- `probe-get_item_flags.gci`: loads.
- `probe-cleared_status_items_flags.gci`: loads.
- `exported-balanced-minus-return.gci`: loads.
- `exported-progress-minus-return.gci`: loads, but current-scene state is
  incomplete; Midna is missing in the reported load test.
- `probe-stage_memory.gci`: loads.
- `probe-visited_room_memory.gci`: loads.
- `probe-event_flags.gci`: loads.

The current `balanced` profile now excludes `player.return_place`, so it has
the same load-safe shape as `exported-balanced-minus-return.gci`.
The current `progress` profile also excludes `player.return_place`, so it has
the same loader-safe shape as `exported-progress-minus-return.gci`.

Focused scene-state probes are available in `probe-exports/` with names starting
`probe-scene_progress_`. They test return-stage/current-stage restoration on
top of the load-safe progress baseline.

Current scene probe results:

- `probe-scene_progress_return_stage_only.gci`: full crash.
- `probe-scene_progress_current_reserve.gci`: loads.
- `probe-scene_progress_stage_only_and_current.gci`: full crash.
- `probe-scene_progress_return_place.gci`: fails to load.
- `probe-scene_progress_return_and_current.gci`: fails to load.
- `probe-scene_progress_gc_gorge_arc_location_bundle.gci`: fails to load.
- `probe-scene_progress_gc_gorge_arc_runtime_location_bundle.gci`: fails to
  load.
- `probe-scene_progress_gc_any_fsp121_location_bundle.gci`: loads, but sense,
  scent, and wolf multi-enemy attack are missing.
- `probe-scene_progress_gc_any_fsp121_runtime_location_bundle.gci`: loads, with
  the same missing wolf abilities.

New GC-reference scene probes graft coherent `F_SP121` location bundles from
known-good GC saves: `probe-scene_progress_gc_gorge_arc_*` and
`probe-scene_progress_gc_any_fsp121_*`.

## Workspace Layout

- Source save packs remain in place for local analysis, but `.gitignore` keeps
  them out of git history.
- Generated `.gci` exports and JSON reports are under `artifacts/`.
- Generated probe GCIs are under `probe-exports/`.
- Git tracks the converter, schema, analysis scripts, and documentation.
