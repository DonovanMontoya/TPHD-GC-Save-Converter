#!/usr/bin/env python3
"""Convert every folder in the published TPHD dungeon pack with curated refs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tphd_to_gci import convert_cemu_save  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "TP Saves (Cemu)")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/dungeon-pack")
    parser.add_argument(
        "--template",
        type=Path,
        default=ROOT / "GameCubeSave/Card A/01-GZ2E-gczelda2.gci",
    )
    args = parser.parse_args()

    references = [
        ROOT / "Twilight Princess Any% Savefiles NTSC",
        ROOT / "TP 100% Saves - NTSC-U 6.17.20",
        ROOT / "references/tpgz-hundo",
    ]
    hints = ROOT / "docs/dungeon-reference-hints.json"
    missing = [path for path in (args.input, args.template, hints, *references) if not path.exists()]
    if missing:
        rendered = ", ".join(str(path) for path in missing)
        raise SystemExit(
            f"Missing required inputs: {rendered}. "
            "Run python3 tools/install_tpgz_references.py for the TPGZ cache."
        )

    args.output.mkdir(parents=True, exist_ok=True)
    folders = sorted(path for path in args.input.iterdir() if path.is_dir())
    if not folders:
        raise SystemExit(f"No dungeon save folders found under {args.input}")

    converted_slots = 0
    for folder in folders:
        output = args.output / f"{folder.name}.gci"
        reports = convert_cemu_save(
            folder,
            args.template,
            output,
            None,
            "safe",
            auto_gc_state_reference_roots=references,
            auto_reference_hints=hints,
        )
        converted_slots += len(reports)
        print(f"Wrote {output} ({len(reports)} slots)")
    print(f"Converted {converted_slots} slots across {len(folders)} GCI files")


if __name__ == "__main__":
    main()
