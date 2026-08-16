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

## Browser version

`web/` contains a dependency-free static converter for GitHub Pages. It runs
entirely in the browser: selected save files are never uploaded or sent to a
server. It supports TPHD → GC with an optional explicit GC checkpoint reference
and the initial experimental GC → TPHD path.

Serve it locally with:

```bash
python3 -m http.server 8000 --directory web
```

The Pages workflow in `.github/workflows/pages.yml` deploys `web/` after it is
enabled under **Repository Settings → Pages → Source: GitHub Actions**. The
workflow follows GitHub's current custom Pages deployment layout.

## Experimental GameCube → TPHD

Reverse conversion requires a checksum-valid TPHD `ZTPxx.dat` template. This
preserves HD-only options, runtime/current-stage state, and tail bytes that have
no GameCube equivalent:

```bash
python3 gci_to_tphd.py input.gci ZTP00-template.dat ZTP00.dat \
  --gc-slot 0 --profile safe
```

`safe` maps identity and basic status, `balanced` adds known inventory/player
structures, and `progress` also maps the structurally compatible stage, visited
room, and event blocks. Every location struct — return place, horse place,
field last stay, and last mark — remains inherited from the TPHD template at all
profiles, matching the forward direction, because cross-version location
grafting is not validated. Reverse
outputs have verified structure and checksums but still require Cemu/TPHD live
gameplay validation; back up the original save before testing.

To install the pinned practice references and convert the entire published
dungeon pack into ten GCI files:

```bash
python3 tools/install_tpgz_references.py
python3 tools/convert_dungeon_pack.py
```

The outputs are written under `artifacts/dungeon-pack/` and remain local.

If the template is not in `GameCubeSave/Card A/01-GZ2E-gczelda2.gci`, pass it:

```bash
python3 tphd_to_gci.py CemuSave exported-balanced.gci \
  --template "/path/to/01-GZ2E-gczelda2.gci"
```

If you have a paired GameCube save at the same story point, use it as a scene
state reference:

```bash
python3 tphd_to_gci.py CemuSave exported-progress-paired.gci \
  --profile progress \
  --gc-state-reference "GameCubeSave/the-legend-of-zelda-twilight-princess.33971.gci" \
  --gc-state-reference-slot 0
```

That keeps mapped TPHD stats/inventory while copying the GC return-place, stage
memory, and event flags from the paired reference.

Location structs — `player.return_place`, `player.horse_place`,
`player.field_last_stay`, and `player.last_mark` — are never taken from TPHD in
either direction. They form one mutually consistent bundle: `field_last_stay`
carries region-discovery bits that pair with visited-room memory, and
`last_mark` holds the Midna warp destination. Grafting part of that bundle
across versions while the rest comes from a different save produces a scene
state that never existed in either, so the whole bundle stays native to the
destination until a paired-save diff validates a translation.

For a collection of GameCube saves, the converter can rank every valid quest-log
slot and choose a same-stage reference automatically. For the included dungeon
pack, also pass its curated exact-hash manifest:

```bash
python3 tools/install_tpgz_references.py
python3 tphd_to_gci.py CemuSave exported-auto.gci \
  --auto-gc-state-reference-root "Twilight Princess Any% Savefiles NTSC" \
  --auto-gc-state-reference-root "TP 100% Saves - NTSC-U 6.17.20" \
  --auto-gc-state-reference-root references/tpgz-hundo \
  --auto-reference-hints docs/dungeon-reference-hints.json
```

The [pack author's description](https://www.reddit.com/r/cemu/comments/l14bdw/zelda_twilight_princess_hd_save_files/)
defines slots 0, 1, and 2 as dungeon entrance, mid-boss, and main boss. It also
explains that Ooccoo was added to the latter checkpoints. Consequently, their
saved return stage can be outside the dungeon and is not a reliable milestone
identifier. `docs/dungeon-reference-hints.json` binds each known source file's
SHA-256 to an annotated GC checkpoint and deliberately rejects a known source
when no equivalent checkpoint exists. The installer downloads five 2.7 KB raw
GameCube quest logs and the GPL license from the official
[TPGZ practice-tool repository](https://github.com/zsrtp/tpgz), pinned to one
commit and verified by SHA-256. Regenerate the hint manifest with
`python3 tools/build_dungeon_hint_manifest.py` after installing those assets.

The curated manifest structurally supports all 30 corpus rows (28 unique save
files). Twenty-seven unique sources use an existing native checkpoint. TPGZ
does not ship a pre-Armogohma body, so the installer deterministically derives
that last reference from its native post-Temple state: it preserves the
Dominion Rod/inventory, clears the documented Temple boss-dead, post-boss-life,
boss-demo, and `F_0267` Temple-clear bits, and sets the native `D_MN06A` boss
return place. That final derived checkpoint is hash-pinned, regression tested,
and live-tested in Dolphin 2606a: it loaded Quest Log 3 into `D_MN06A`, played
the Armogohma introduction, and entered controllable boss gameplay with the
Dominion Rod equipped. Without a matching hash hint, automatic mode falls back
to ranking and rejects a slot when there is no exact-stage match or when the
top-two score margin is below 50 (configurable with
`--auto-reference-min-margin`).

Automatic reference mode starts from the selected reference's entire coherent
GC quest state, then overlays only TPHD health, rupees, oil, names, play time,
death count, and clear count. This avoids mixing mutually dependent dungeon,
inventory, location, and event structures. The normal profile choice does not
expand the overlay while automatic reference mode is active. The Forest Temple
entrance and derived Armogohma checkpoint were validated in Dolphin 2606a
through live gameplay; exact inputs, hashes, and observations are recorded in
`docs/dolphin-test-log.md`.

## Profiles

- `safe`: most likely to load. Copies player/horse names, health, rupees, play
  time, death count, and clear count. Most progression remains from the GC
  template.
- `balanced`: experimental. Adds inventory, item flags, item counts,
  collectibles, letters, fishing, minigame records, and GC-normalized wolf
  scent/sense/Midna attack flags when TPHD scent state is present. It does not
  map location structs; no profile does. To move location state, supply a
  paired GC reference, which grafts its return place.
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
sample save. The current balanced and progress profiles skip the unsafe
`player.return_place` direct copy; both have a load-tested shape, but progress
still needs semantic validation across more saves.

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

The current `balanced` and `progress` profiles exclude every location rule, not
just `player.return_place`, so they no longer share a shape with
`exported-balanced-minus-return.gci` or `exported-progress-minus-return.gci`.
Those artifacts still carried `player.horse_place`, `player.field_last_stay`,
and `player.last_mark` from TPHD, so their load results are not evidence for
the current mapping.

The load evidence for the shape that ships today is the 2026-08-14
re-validation in `docs/dolphin-test-log.md`: a regenerated paired `progress`
export reached `F_SP121` room 2 and went on to load actor archives, so it
reaches live gameplay rather than stalling in a menu. That run is a stage/room
load observation on the Null backend and does not by itself verify rupees,
scent, or Midna riding.

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
- `probe-scene_progress_gc_any_fsp121_return_only.gci`: loads, but the state is
  missing bridge/light/portal progression and asks for bridge repair without
  usable warp points.

New GC-reference scene probes graft coherent `F_SP121` location bundles from
known-good GC saves: `probe-scene_progress_gc_gorge_arc_*` and
`probe-scene_progress_gc_any_fsp121_*`.

Current location status: not solved. Direct TPHD `player.return_place` is
unsafe, return-stage-only crashes, and the exact TPHD `F_SP121/0x06/0x03`
return tuple does not work just because the tuple itself is valid. The converter
deliberately keeps template `return_place`/reserve data until this is translated
rather than copied.

Wolf ability probes are also available in `probe-exports/` with names starting
`probe-wolf_ability_`. They start from the load-tested progress plus Any%
`F_SP121` scene bundle and graft suspected ability-state ranges from known
wolf/Midna GC references.

Targeted GC-decomp probes with names starting `probe-ability_flags_` and
`probe-scent_` confirmed the important pieces for the current sample. The
converter now derives GC wolf ability state when TPHD has a known scent item:
current scent is written to GC `status_a.equipment[3]`, the scent item-first
bit is set, wolf sense flag `0x4308` is set, and the tested pair
`0x0501 + 0x0C10` restores the Midna multi-target attack.

Next useful tests are location-specific probes, starting from the known-loading
Any% `F_SP121` location bundle and changing only one return/start/room/current
field at a time.

Generated focused probes:

- `probe-scene_progress_any_fsp121_return_player_status_from_hd.gci`
- `probe-scene_progress_any_fsp121_return_room_from_hd.gci`
- `probe-scene_progress_any_fsp121_field_last_stay_from_hd.gci`
- `probe-scene_progress_any_fsp121_horse_place_from_hd.gci`
- `probe-scene_progress_any_fsp121_current_reserve_from_hd.gci`

The local `tp/` decomp confirms that GC boot uses `player.return_place` to call
`dComIfGp_setNextStage()`. Runtime `dSv_restart_c` is outside the persisted GCI
quest-log body, so current-position restoration cannot be solved by copying an
HD runtime block into the GC reserve area.

Follow-up bridge/portal probes on the Any% return-only baseline are generated
with names starting `probe-scene_progress_gc_any_fsp121_return_only_`. Test the
single-flag probes first, then `gorge_bridge_flags`, then the stage-memory
variants if warp map icons are still missing.

Current short-list test result: `02-warp-mode.gci`, `03-bridge-flags.gci`, and
`04-portal-icons.gci` all work as intended. `02-warp-mode.gci` also adds the
transform option because it includes shadow-crystal flag `M_077 = 0x0D04`.
`05-current-best.gci` combines the working portal-icon state with that transform
gate as a probe only. This state is intentionally not promoted into the normal
converter because it grants transform/warp/bridge progression not proven to be
present in the TPHD source save.

Paired GC reference result:
`GameCubeSave/the-legend-of-zelda-twilight-princess.33971.gci` slot 0 is a
wooden-sword-scent GC save at the same story point. The generated
`artifacts/exports/exported-progress-paired-wood-scent.gci` matches that
reference for return place, event gates, and relevant stage switches while
keeping TPHD stats and inventory.

This paired export was validated in Dolphin 2606a against the NTSC-U `GZ2E01`
disc on 2026-08-11. It appears in Quest Log 1 and loads into live `F_SP121`
gameplay as wolf Link with Midna riding, Sense available, and the mapped 299
rupees. Exact hashes and observations are recorded in
`docs/dolphin-test-log.md`.

Before testing a probe in Dolphin, inspect it:

```bash
python3 inspect_gci_state.py \
  probe-exports/probe-scene_progress_gc_any_fsp121_return_only_portal_core_flags.gci \
  --compare probe-exports/probe-scene_progress_gc_any_fsp121_return_only.gci
```

The inspector prints the return tuple, relevant event gates, and stage switch
words. For portal work, Dolphin testing should answer only these questions:

- Does the file load?
- Does Midna/warp mode become available?
- Do portal destination icons appear?
- Does the game still ask for bridge repair?

If the inspector shows no changed event or stage-switch gate for the question,
do not spend time testing that probe.

## Workspace Layout

- Source save packs remain in place for local analysis, but `.gitignore` keeps
  them out of git history.
- Generated `.gci` exports and JSON reports are under `artifacts/`.
- Generated probe GCIs are under `probe-exports/`.
- Git tracks the converter, schema, analysis scripts, and documentation.

## Development

Run the complete dependency-free check suite with:

```bash
python3 tools/check.py
```

This compiles the Python sources, runs synthetic unit/integration tests, and,
when the ignored local save fixtures are available, reproduces the known paired
GC-reference artifact byte-for-byte and inspects its scene state. GitHub Actions
runs the portable portion on Python 3.10 through 3.13.

Automated checks prove file structure and mapping invariants, not gameplay.
Focused Dolphin results belong in `docs/dolphin-test-log.md`.

For an isolated emulator boot test, supply your legally dumped NTSC-U game
image. The harness mounts the converted GCI in a temporary Dolphin user folder,
leaving normal Dolphin settings and saves untouched. It always forces Dolphin's
volume to zero:

```bash
python3 tools/dolphin_smoke.py \
  --game "/path/to/your/Twilight Princess image.rvz" \
  --gci artifacts/exports/exported-progress-paired-wood-scent.gci
```

Add `--movie tests/dolphin/load-slot-0.dtm` once a deterministic input movie is
recorded for the exact game revision. Alternatively, `--input-script` accepts
timestamped native GameCube controller commands without relying on keyboard
focus; for example, a line `12.0 PRESS START` followed by
`12.08 RELEASE START`. Use `--video-backend Metal` for a visible validation
run. The harness stores the exact command and controller trace under
`artifacts/dolphin-smoke/`. A boot without deterministic input does not prove
that gameplay loaded from the save. Add `--expect-disc-path D_MN06A` to enable
Dolphin's disc file monitor and make the run fail unless the game actually
loads that stage's files; the evidence is saved as `disc-paths.log`.

To run that stage-load assertion across every slot in the generated dungeon
pack, use the unattended batch wrapper (all launches are isolated and muted):

```bash
python3 tools/dolphin_validate_pack.py \
  --game "/path/to/your/Twilight Princess image.rvz" \
  --keep-going
```

Each probe duplicates one checkpoint across all three menu positions, removing
save-menu selection as a source of ambiguity. Progress is resumable with
`--start`; machine-readable results and per-run disc-path evidence are kept in
`artifacts/dolphin-pack-validation/`.

The completed unattended audit passed 30/30 exact-stage checks: every converted
checkpoint loaded its encoded return stage in Dolphin with no mismatch or
loader failure. Forest Temple and Armogohma also have focused visible-gameplay
observations. Exact-stage loading is strong compatibility evidence, but it does
not by itself prove every quest event remains semantically correct during
extended play.
