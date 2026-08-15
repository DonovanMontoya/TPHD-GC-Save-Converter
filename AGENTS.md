# Project Operating Instructions

This repository reverse-engineers and converts Twilight Princess HD save data
to the GameCube save format. Treat byte mappings as evidence-backed claims.

## Required development loop

1. Read `README.md`, `docs/save-format-map.md`, and
   `docs/gc-reference-findings.md` before changing conversion behavior.
2. Put conversion mappings in `save_schema.py`; do not add unexplained broad
   byte copies directly to `tphd_to_gci.py`.
3. Add or update automated tests for every behavior change.
4. Run `python3 tools/check.py` before handing off work.
5. Keep generated `.gci`, raw `.dat`, save packs, ROMs, and emulator state out
   of git.

## Evidence levels

- A valid checksum proves only structural integrity.
- A save visible in Dolphin proves only that the GCI wrapper is readable.
- A save loading proves loader compatibility, not correct gameplay semantics.
- Promote a mapping only after a controlled paired-save diff or a matching GC
  decomp fact plus a focused Dolphin observation.

Never describe a conversion as fully working based only on automated tests.
Record manual emulator results in `docs/dolphin-test-log.md` using the supplied
template and keep each probe focused on one question.

## Safety invariants

- Preserve the GCI metadata/template outside the selected quest-log slots.
- Recompute and verify both GC checksum words for every patched slot.
- Never directly copy TPHD `player.return_place`, configuration, reserve, or
  HD-only tail bytes without a validated translation.
- Paired GC references may supply only explicitly documented GC-native state.
- Do not infer story progression that the TPHD source does not prove.

## Commands

```bash
python3 tools/check.py
python3 -m unittest discover -s tests -v
python3 tphd_to_gci.py --help
```

If local ignored fixtures are present, `tools/check.py` also reproduces and
checks the known paired-reference export.
