#!/usr/bin/env python3
"""Run dependency-free project checks and optional local-fixture regressions."""

from __future__ import annotations

import compileall
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*command: str) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_fixture_regression() -> None:
    hd = ROOT / "CemuSave/1019e500/user/80000001/ZTP00.dat"
    template = ROOT / "GameCubeSave/Card A/01-GZ2E-gczelda2.gci"
    reference = ROOT / "GameCubeSave/the-legend-of-zelda-twilight-princess.33971.gci"
    expected = ROOT / "artifacts/exports/exported-progress-paired-wood-scent.gci"
    required = (hd, template, reference, expected)
    missing = [path.relative_to(ROOT) for path in required if not path.is_file()]
    if missing:
        print("Local fixture regression: SKIP (missing ignored fixtures: " + ", ".join(map(str, missing)) + ")")
        return

    with tempfile.TemporaryDirectory(prefix="tphd-gci-check-") as directory:
        output = Path(directory) / "paired.gci"
        run(
            sys.executable,
            "tphd_to_gci.py",
            str(hd),
            str(output),
            "--template",
            str(template),
            "--profile",
            "progress",
            "--gc-state-reference",
            str(reference),
            "--gc-state-reference-slot",
            "0",
        )
        if output.read_bytes() != expected.read_bytes():
            raise RuntimeError(
                "paired-reference artifact changed: "
                f"expected sha256={sha256(expected)}, actual sha256={sha256(output)}"
            )
        run(sys.executable, "inspect_gci_state.py", str(output), "--compare", f"{reference}:0:paired-reference")
        print(f"Local fixture regression: PASS (sha256={sha256(output)})")


def automatic_reference_corpus_regression() -> None:
    hd_root = ROOT / "TP Saves (Cemu)"
    reference_roots = (
        ROOT / "Twilight Princess Any% Savefiles NTSC",
        ROOT / "TP 100% Saves - NTSC-U 6.17.20",
        ROOT / "references/tpgz-hundo",
    )
    template_path = ROOT / "GameCubeSave/Card A/01-GZ2E-gczelda2.gci"
    hint_path = ROOT / "docs/dungeon-reference-hints.json"
    required = (hd_root, template_path, hint_path, *reference_roots)
    if not all(path.exists() for path in required):
        print("Automatic-reference corpus regression: SKIP (local save collections unavailable)")
        return

    sys.path.insert(0, str(ROOT))
    from gc_reference_matcher import load_reference_hints, load_reference_slots
    from tphd_to_gci import (
        GC_QUEST_LOG_OFFSETS,
        GC_QUEST_LOG_SIZE,
        build_mapped_body,
        convert_cemu_save,
        validate_hd_slot,
        verify_gc_slot,
    )

    references = load_reference_slots(list(reference_roots))
    hints = load_reference_hints(hint_path)
    template = template_path.read_bytes()
    supported = unsupported = 0
    for hd_path in sorted(hd_root.rglob("ZTP0[0-2].dat")):
        hd = hd_path.read_bytes()
        validate_hd_slot(hd, str(hd_path))
        hd_sha256 = hashlib.sha256(hd).hexdigest()
        hint = hints.get(hd_sha256)
        if hint is None:
            raise RuntimeError(f"curated reference manifest does not cover {hd_path}")
        if hint.unsupported_reason is not None:
            unsupported += 1
            continue
        selected = next(
            (
                reference
                for reference in references
                if reference.file_sha256 == hint.reference_sha256
                and reference.slot == hint.reference_slot
            ),
            None,
        )
        if selected is None:
            raise RuntimeError(
                f"curated reference {hint.reference_sha256} slot {hint.reference_slot} "
                f"for {hd_path} is unavailable"
            )
        quest_log = template[GC_QUEST_LOG_OFFSETS[0] : GC_QUEST_LOG_OFFSETS[0] + GC_QUEST_LOG_SIZE]
        body, _report = build_mapped_body(
            hd,
            quest_log,
            0,
            0,
            "safe",
            selected.body,
            "corpus regression",
            True,
        )
        if len(body) != GC_QUEST_LOG_SIZE - 8:
            raise RuntimeError(f"automatic-reference body has wrong size for {hd_path}")
        supported += 1

    result = (supported, unsupported)
    if result != (30, 0):
        raise RuntimeError(f"curated corpus decisions changed: expected (30, 0), got {result}")

    with tempfile.TemporaryDirectory(prefix="tphd-corpus-check-") as directory:
        output_root = Path(directory)
        for folder in sorted(path for path in hd_root.iterdir() if path.is_dir()):
            output = output_root / f"{folder.name}.gci"
            reports = convert_cemu_save(
                folder,
                template_path,
                output,
                None,
                "safe",
                auto_gc_state_reference_roots=list(reference_roots),
                auto_reference_hints=hint_path,
            )
            converted = output.read_bytes()
            if len(reports) != 3 or not all(verify_gc_slot(converted, slot) for slot in range(3)):
                raise RuntimeError(f"end-to-end corpus conversion failed for {folder}")
    print(
        "Automatic-reference corpus regression: PASS "
        f"({supported} curated references built, {unsupported} explicitly unsupported)"
    )


def dolphin_self_check() -> None:
    dolphin = Path("/Applications/Dolphin.app/Contents/MacOS/Dolphin")
    if not dolphin.is_file() and shutil.which("dolphin-emu") is None and shutil.which("Dolphin") is None:
        print("Dolphin self-check: SKIP (Dolphin is not installed)")
        return
    run(sys.executable, "tools/dolphin_smoke.py", "--self-check")


def main() -> None:
    print("Compiling Python sources", flush=True)
    if not compileall.compile_dir(ROOT, quiet=1, rx=re.compile(r"/tp/")):
        raise SystemExit("Python compilation failed")
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v")
    node = shutil.which("node")
    if node is None:
        print("Browser converter tests: SKIP (Node.js is not installed)")
    else:
        run(node, "--test", "tests/web_converter.test.mjs")
    local_fixture_regression()
    automatic_reference_corpus_regression()
    dolphin_self_check()
    print("All available checks passed")


if __name__ == "__main__":
    main()
