# TPHD Full Mapping Protocol

The goal is to promote every TPHD byte from `unknown` or `structural` to a
confirmed field or confirmed padding/HD-only state. A single save cannot prove
meaning; each field needs controlled before/after evidence.

## Required Save Pairs

Make a backup before each test. For each test, change exactly one thing, save,
then run `diff_cemu_saves.py`.

1. **Health**
   - Change current health only by taking damage.
   - Change max health only by collecting a heart container/piece if possible.

2. **Rupees**
   - Add a known amount, preferably +1 and +10 in separate saves.

3. **Oil**
   - Use lantern oil or refill oil without changing inventory.

4. **Equipment**
   - Change equipped sword, shield, clothes, and current form if available.

5. **Selected Items**
   - Change only the active item slots/control bindings.

6. **Wallet / Ammo**
   - Change wallet upgrade state, arrows, bomb counts, bottle contents.

7. **Position / Return Place**
   - Save in a different stage, room, spawn, and layer.

8. **Event Flags**
   - Trigger one simple event flag, such as opening a single chest or talking to
     one NPC that sets a persistent flag.

9. **Stage Memory**
   - Toggle a single dungeon switch/chest/item state.

10. **HD-only Features**
    - Hero Mode, amiibo/Cave of Shadows, stamps, Ghost Lantern or any HD-only
      option/state.

## Commands

Generate the current full byte map:

```bash
python3 generate_byte_map.py docs/cemu-byte-map.csv \
  --sample CemuSave/1019e500/user/80000001/ZTP00.dat
```

Diff two controlled saves:

```bash
python3 diff_cemu_saves.py before/ZTP00.dat after/ZTP00.dat
```

Recalculate coverage:

```bash
python3 schema_coverage.py
```

## Promotion Rules

- `unknown` -> `observed`: at least one controlled diff identifies the byte and
  value encoding.
- `structural` -> `observed`: controlled diff shows the GC bit/field has the
  same semantic meaning in TPHD.
- `observed` -> `known`: multiple independent saves confirm stable offset and
  encoding, or a primary source/decomp identifies the field.
- `unknown` -> `padding`: multiple saves show the range is always zero or
  ignored by TPHD.
- `unknown` -> `hd_only`: field changes with an HD feature and has no GC
  destination.
