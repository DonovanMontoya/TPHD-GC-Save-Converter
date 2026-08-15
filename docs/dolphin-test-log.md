# Dolphin Validation Log

Automated tests validate mapping boundaries, wrapper preservation, and
checksums. They cannot prove that a converted save loads into correct gameplay.
Record focused emulator observations here.

## Environment

| Field | Value |
| --- | --- |
| Dolphin version | 2606a installed via the official Homebrew cask on 2026-08-11 |
| Game region/revision | NTSC-U / `GZ2E01` references |
| Host | macOS |

## Result template

```text
Date:
Commit:
Dolphin version:
Input TPHD save identifier/hash:
Template GCI identifier/hash:
Paired GC reference identifier/hash (if any):
Output profile:
Probe/output file:

Visible in save list? yes/no
Loads into gameplay? yes/no
Expected stage/room/spawn:
Observed stage/room/spawn:
Expected health/rupees/inventory:
Observed health/rupees/inventory:
Expected wolf/scent/Midna abilities:
Observed wolf/scent/Midna abilities:
Expected story/portal/bridge state:
Observed story/portal/bridge state:
Unexpected behavior:
Conclusion:
```

## Existing observations

The historical probe results are summarized in `README.md` and
`docs/gc-reference-findings.md`. New testing should add dated entries here so
future mapping decisions have an auditable environment and input identity.

## 2026-08-11 — Paired wooden-sword-scent export

```text
Date: 2026-08-11
Commit: 6ec8bc9ba433ac197d1909f69b245b2684aaf33d plus local test-harness changes
Dolphin version: 2606a, JITARM64 SC, Metal, HLE
Game: NTSC-U GZ2E01 ISO
Game SHA-256: 490ef919f413e00daedb4711777c3be05ef9afc12c7acca7675c721c9393c814
Input TPHD save: CemuSave/1019e500/user/80000001/ZTP00.dat
Template SHA-256: dc3239255b22525b50275c872f02b6629088d5790c5f789595b0d0731820ac70
Paired GC reference SHA-256: 1871bb607c10c38ec5d1f52d077b965a0f45020e163fca48269f58c408b360cb
Output profile: progress plus paired GC state reference slot 0
Output SHA-256: fce289927e581c222dc0bbc64dc28e19216c5d8659300e2f5a20fb72e7293314

Visible in save list? yes
Loads into gameplay? yes
Expected stage/room/spawn: paired F_SP121 return tuple, point 1, room 2
Observed stage/room/spawn: loaded into F_SP121 as wolf Link with Midna riding
Expected health/rupees/inventory: mapped TPHD state, 299 rupees
Observed health/rupees/inventory: save list rendered mapped equipment; gameplay showed 299 rupees
Expected wolf/scent/Midna abilities: children scent, sense, Midna riding/multi-target gates
Observed wolf/scent/Midna abilities: Midna riding and Sense prompt visibly present
Expected story/portal/bridge state: paired early Forest Temple/portal state
Observed story/portal/bridge state: not exhaustively exercised in this pass
Unexpected behavior: first isolated Dolphin profile displayed the normal TV Settings screen once
Conclusion: paired-reference export is loader-compatible and reaches live gameplay with the key mapped state visible
```

Evidence screenshot: `artifacts/dolphin-smoke/paired-gameplay.png` (local,
git-ignored).

## 2026-08-11 — Automatic Forest Temple reference

```text
Date: 2026-08-11
Dolphin version: 2606a, JITARM64 SC, Metal, HLE
Game: NTSC-U GZ2E01 ISO
Game SHA-256: 490ef919f413e00daedb4711777c3be05ef9afc12c7acca7675c721c9393c814
Input TPHD save: TP Saves (Cemu)/1.Dungeon (Forest Temple)/00050000/1019e600/user/80000001/ZTP00.dat
Input SHA-256: d3c103d45d46c04074056b0970f9133d4d269263530ba13085a6314bd384b34c
Automatically selected reference: TP 100% Saves - NTSC-U 6.17.20/03 - FT, FT 2, Diababa.gci slot 0
Reference SHA-256: 77fdd0d45570822b194c89ccc1fbaa05106eccb8c3d4e856a63af0e3e7ac27c5
Matcher score/margin: 424 / 78
Output SHA-256: 2c53642bf2dc0c71141f4dee401f88e77d888f622232a7606b7ac002f75500fc

Visible in save list? yes (Quest Log 1, Link)
Loads into gameplay? yes
Observed stage: Forest Temple (D_MN05 reference state)
Observed rupees: 010, matching the TPHD overlay
Observed equipment/state: coherent Forest Temple reference inventory and dungeon state
Unexpected behavior: none observed during the load check
Conclusion: automatic full-reference state plus the conservative TPHD identity/basic-stat overlay is loader-compatible for this dungeon save
```

Evidence screenshot: `artifacts/dolphin-smoke/auto-forest-temple-gameplay.png`
(local, git-ignored; SHA-256
`a6f0f3d9c338dc962d98a4412e5417310b0e783bd9fc6726427e444362955ea2`).

## 2026-08-11 — Derived pre-Armogohma checkpoint

```text
Date: 2026-08-11
Dolphin version: 2606a, JITARM64 SC, Metal, HLE
Game: NTSC-U GZ2E01 RVZ
Input TPHD save: TP Saves (Cemu)/6.Dungeon (Temple of Time)/00050000/1019e600/user/80000001/ZTP02.dat
Input SHA-256: 862e84f1fb4e0fd6f92c0009d168df34cdc02151a58fa1855c18389a05a73423
Automatically selected reference: references/tpgz-hundo/armogohma-derived.bin
Reference SHA-256: fb17a0f972db3299fbd25f4ce77eb385d79e7376b4f294458a602cd0059abacc
Output: artifacts/dungeon-pack/6.Dungeon (Temple of Time).gci, slot 2 / Quest Log 3
Output SHA-256: 0e0d7d9d806c860179808837076493b703fc21ceee3908bd8fc513fdc6b5c91a

Visible in save list? yes (Quest Log 3)
Loads into gameplay? yes
Expected stage/room/spawn: D_MN06A, point 0, room 50
Observed stage/room/spawn: loaded at the Armogohma arena entrance
Expected health/rupees/inventory: coherent post-Temple native inventory with Dominion Rod retained
Observed health/rupees/inventory: gameplay HUD appeared; 1078 rupees; Dominion Rod visibly equipped to Y
Expected boss state: boss alive, introductory sequence available, Temple clear event removed
Observed boss state: Armogohma introduction played and transitioned into controllable boss gameplay
Unexpected behavior: normal TV Settings prompt appeared once for the isolated Dolphin profile
Conclusion: the deterministic pre-Armogohma derivation is loader-compatible and reaches the intended live boss encounter with its required item available
```

The native-pipe replay was then repeated unattended with
`tests/dolphin/load-slot-2-first-run.txt` and the Dolphin file monitor enabled.
The machine assertion observed both `res/Stage/D_MN06A/STG_00.arc` and
`res/Stage/D_MN06A/R50_00.arc`, as well as `d_a_b_gm.rel` and `B_gm.arc` for
the Armogohma actor. The trace and complete disc-path log are under
`artifacts/dolphin-smoke/automated-armogohma/`.

Evidence screenshots (local, git-ignored):

- `artifacts/dolphin-smoke/armogohma-derived-boss-intro.jpeg`, SHA-256 `339d47f17f83734aa24c7ca216b7b15d815fa90a3fbaee7eb0ad5108bef6d4f9`
- `artifacts/dolphin-smoke/armogohma-derived-gameplay.jpeg`, SHA-256 `ee13852c8a1285e51ea68643244fda565e9b52af8401e885601a3454136ac4b1`

## 2026-08-11 — Unattended pack stage-load batch 1

`tools/dolphin_validate_pack.py --limit 8 --keep-going` completed 8/8 exact
stage assertions using isolated, muted Dolphin profiles. The validated jobs were:

- Forest Temple entrance and mid-dungeon: `D_MN05`, `D_MN05`
- Forest Temple boss: `D_MN05A`
- Goron Mines entrance, mid-boss, and boss: `D_MN04`, `D_MN04B`, `D_MN04A`
- Lakebed Temple entrance and mid-boss: `D_MN01`, `D_MN01B`

Each result has an exact controller trace, launch command, and Dolphin disc-path
log under `artifacts/dolphin-pack-validation/`. The resumable machine-readable
summary is `artifacts/dolphin-pack-validation/summary.json`.

## 2026-08-11 — Unattended pack stage-load batch 2

The resumed audit (`--start 8 --limit 8`) also completed 8/8 exact-stage
assertions:

- Lakebed Temple boss: `D_MN01A`
- Arbiter's Grounds entrance, mid-boss, and boss: `D_MN10`, `D_MN10B`, `D_MN10A`
- Snowpeak Ruins entrance, mid-boss, and boss: `D_MN11`, `D_MN11B`, `D_MN11A`
- Temple of Time entrance: `D_MN06`

The cumulative unattended result is 16/16 checkpoint loads, with no stage
mismatch or loader failure.

## 2026-08-11 — Unattended pack stage-load batches 3 and 4

The final resumed batches (`--start 16 --limit 8`, then
`--start 24 --limit 6`) completed the corpus:

- Temple of Time mid-dungeon and boss: `D_MN06`, `D_MN06A`
- City in the Sky entrance, mid-boss, and boss: `D_MN07`, `D_MN07B`, `D_MN07A`
- Palace of Twilight entrance, mid-dungeon, and boss: `D_MN08`, `D_MN08`, `D_MN08A`
- Hyrule Castle entrance, mid-dungeon, and boss: `D_MN09`, `D_MN09`, `D_MN09A`
- Hidden Village bonus slots: `F_SP128`, `D_MN06`, `D_MN06A`

Final result: **30/30 converted checkpoint slots loaded their expected stage in
Dolphin**, with no stage mismatch or loader failure. This proves loader and
return-stage compatibility; it does not replace extended gameplay testing of
every quest-state detail.
