#!/usr/bin/env python3
"""Build curated hash hints for the local three-milestone TPHD dungeon pack.

The pack author documents each dungeon folder as entrance, mid-boss, and main
boss in slots 0, 1, and 2. Mid-boss/boss saves use Ooccoo, so their persisted
return stage can point outside the dungeon and must not drive reference choice.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HD_ROOT = ROOT / "TP Saves (Cemu)"
OUTPUT = ROOT / "docs/dungeon-reference-hints.json"
SOURCE_URL = "https://www.reddit.com/r/cemu/comments/l14bdw/zelda_twilight_princess_hd_save_files/"


def mapped(reference: str, slot: int, note: str) -> tuple[str, int, str]:
    return reference, slot, note


# Folder names are stable identifiers from the published TPHD pack. Reference
# paths point at the two annotated GC collections and the hash-pinned TPGZ
# practice saves already used by the matcher.
MILESTONES: dict[str, tuple[tuple[str, int, str] | str, ...]] = {
    "1.Dungeon (Forest Temple)": (
        mapped("TP 100% Saves - NTSC-U 6.17.20/03 - FT, FT 2, Diababa.gci", 0, "Forest Temple entrance"),
        mapped("TP 100% Saves - NTSC-U 6.17.20/03 - FT, FT 2, Diababa.gci", 1, "Forest Temple mid-dungeon"),
        mapped("TP 100% Saves - NTSC-U 6.17.20/03 - FT, FT 2, Diababa.gci", 2, "Diababa boss"),
    ),
    "2.Dungeon (Goron Mines)": (
        mapped("TP 100% Saves - NTSC-U 6.17.20/07 - KB2 skip, Coro TD, GM.gci", 2, "Goron Mines entrance"),
        mapped("references/tpgz-hundo/dangoro.bin", 0, "Dangoro mid-boss (TPGZ hundo practice save)"),
        mapped("references/tpgz-hundo/fyrus.bin", 0, "Fyrus boss (TPGZ hundo practice save)"),
    ),
    "3.Dungeon (Lakebed Temple)": (
        mapped("TP 100% Saves - NTSC-U 6.17.20/05 - Post IB, Pillar Clip, Lakebed.gci", 2, "Lakebed entrance"),
        mapped("Twilight Princess Any% Savefiles NTSC/5 PillarClip-Lakebed1-DekuToad.gci", 2, "Deku Toad mid-boss"),
        mapped("Twilight Princess Any% Savefiles NTSC/8 FreezardSkip-LakebedBKSkip-Morpheel.gci", 2, "Morpheel boss"),
    ),
    "4.Dungeon (Arbiter’s Grounds)": (
        mapped("Twilight Princess Any% Savefiles NTSC/10 Arbiters1-Poe1Skip-DeathSword.gci", 0, "Arbiter's Grounds entrance"),
        mapped("Twilight Princess Any% Savefiles NTSC/10 Arbiters1-Poe1Skip-DeathSword.gci", 2, "Death Sword mid-boss"),
        mapped("Twilight Princess Any% Savefiles NTSC/11 Arbiters2-Stallord-MirrorChamber.gci", 1, "Stallord boss"),
    ),
    "5.Dungeon (Snowpeak Ruins)": (
        mapped("TP 100% Saves - NTSC-U 6.17.20/12 - SPR1, SPR2, Bomb Boost.gci", 0, "Snowpeak Ruins entrance"),
        mapped("references/tpgz-hundo/darkhammer.bin", 0, "Darkhammer mid-boss (TPGZ hundo practice save)"),
        mapped("references/tpgz-hundo/blizzeta.bin", 0, "Blizzeta boss (TPGZ hundo practice save)"),
    ),
    "6.Dungeon (Temple of Time)": (
        mapped("TP 100% Saves - NTSC-U 6.17.20/13 - ToT1, ToT2, Post ToT.gci", 0, "Temple of Time entrance"),
        mapped("TP 100% Saves - NTSC-U 6.17.20/13 - ToT1, ToT2, Post ToT.gci", 1, "Temple of Time mid-dungeon"),
        mapped("references/tpgz-hundo/armogohma-derived.bin", 0, "Armogohma boss (derived from native TPGZ post-ToT state)"),
    ),
    "7.Dungeon (City in the Sky)": (
        mapped("TP 100% Saves - NTSC-U 6.17.20/15 - Ice Puzzle, HV1, City 1.gci", 2, "City in the Sky entrance"),
        mapped("Twilight Princess Any% Savefiles NTSC/12 EarlyCitS-CitS1-ArealfosSkip.gci", 2, "Aeralfos mid-boss"),
        mapped("Twilight Princess Any% Savefiles NTSC/13 CitS2-FanTower-Argorok.gci", 2, "Argorok boss"),
    ),
    "8.Dungeon (Palace of Twilight)": (
        mapped("TP 100% Saves - NTSC-U 6.17.20/17 - Post City, Palace1, Palace2.gci", 1, "Palace of Twilight entrance"),
        mapped("TP 100% Saves - NTSC-U 6.17.20/17 - Post City, Palace1, Palace2.gci", 2, "Palace of Twilight after both Sols"),
        mapped("TP 100% Saves - NTSC-U 6.17.20/18 - Zant, CoO, Post CoO.gci", 0, "Zant boss"),
    ),
    "9.Dungeon (Hyrule Castle)": (
        mapped("TP 100% Saves - NTSC-U 6.17.20/19 - Cats, Hyrule, Beast Ganon.gci", 1, "Hyrule Castle entrance"),
        mapped("references/tpgz-hundo/hc_darknut.bin", 0, "Hyrule Castle Darknut mid-boss (TPGZ hundo practice save)"),
        mapped("TP 100% Saves - NTSC-U 6.17.20/19 - Cats, Hyrule, Beast Ganon.gci", 2, "Puppet Zelda final-boss sequence"),
    ),
    "Bonus (Hidden Village Quest)": (
        mapped("TP 100% Saves - NTSC-U 6.17.20/15 - Ice Puzzle, HV1, City 1.gci", 1, "Hidden Village quest"),
        mapped("TP 100% Saves - NTSC-U 6.17.20/13 - ToT1, ToT2, Post ToT.gci", 1, "Temple of Time mid-dungeon"),
        mapped("references/tpgz-hundo/armogohma-derived.bin", 0, "Armogohma boss (derived from native TPGZ post-ToT state)"),
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def slot_path(folder: str, slot: int) -> Path:
    return HD_ROOT / folder / "00050000/1019e600/user/80000001" / f"ZTP0{slot}.dat"


def main() -> None:
    entries_by_hash: dict[str, dict[str, object]] = {}
    for folder, milestones in MILESTONES.items():
        for slot, milestone in enumerate(milestones):
            hd_path = slot_path(folder, slot)
            hd_sha256 = sha256(hd_path)
            entry: dict[str, object] = {"hd_sha256": hd_sha256}
            if isinstance(milestone, str):
                entry["unsupported_reason"] = milestone
            else:
                reference_path, reference_slot, note = milestone
                entry.update(
                    {
                        "reference_sha256": sha256(ROOT / reference_path),
                        "reference_slot": reference_slot,
                        "note": note,
                    }
                )
            previous = entries_by_hash.get(hd_sha256)
            if previous is not None and previous != entry:
                raise RuntimeError(f"Conflicting milestone hints for duplicate TPHD save {hd_sha256}")
            entries_by_hash[hd_sha256] = entry

    document = {
        "version": 1,
        "source": SOURCE_URL,
        "description": "Curated entrance/mid-boss/boss mappings for the published TPHD dungeon save pack.",
        "entries": sorted(entries_by_hash.values(), key=lambda entry: str(entry["hd_sha256"])),
    }
    OUTPUT.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    supported = sum("reference_sha256" in entry for entry in entries_by_hash.values())
    unsupported_count = len(entries_by_hash) - supported
    print(f"Wrote {OUTPUT.relative_to(ROOT)}: {supported} supported, {unsupported_count} unsupported unique saves")


if __name__ == "__main__":
    main()
