#!/usr/bin/env python3
"""Unattended, muted Dolphin stage-load validation for every GCI pack slot."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tphd_to_gci import patch_slot, quest_log_body_from_gci
from tools.dolphin_smoke import find_dolphin, run_dolphin, validate_inputs


DEFAULT_INPUT_SCRIPT = ROOT / "tests/dolphin/load-slot-2-first-run.txt"


def stage_name(body: bytes) -> str:
    raw = body[0x058:0x060].split(b"\0", 1)[0]
    try:
        stage = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError(f"return-place stage is not ASCII: {raw.hex()}") from error
    if not stage or not re.fullmatch(r"[A-Z0-9_]+", stage):
        raise ValueError(f"invalid return-place stage {stage!r}")
    return stage


def duplicate_slot(gci: bytes, source_slot: int) -> bytes:
    """Return a probe wrapper in which every menu slot is the target checkpoint."""
    body = quest_log_body_from_gci(gci, source_slot)
    probe = bytearray(gci)
    for destination_slot in range(3):
        patch_slot(probe, body, destination_slot)
    return bytes(probe)


def discover_jobs(pack: Path) -> list[tuple[Path, int, str]]:
    jobs: list[tuple[Path, int, str]] = []
    for gci_path in sorted(pack.glob("*.gci")):
        gci = gci_path.read_bytes()
        for slot in range(3):
            jobs.append((gci_path, slot, stage_name(quest_log_body_from_gci(gci, slot))))
    if not jobs:
        raise FileNotFoundError(f"no .gci files found in {pack}")
    return jobs


def recover_completed_results(
    artifacts: Path, jobs: list[tuple[Path, int, str]]
) -> dict[int, dict[str, object]]:
    """Rebuild successful rows from durable per-run evidence after interruption."""
    recovered: dict[int, dict[str, object]] = {}
    for index, (gci_path, slot, expected_stage) in enumerate(jobs):
        matches = sorted(artifacts.glob(f"{index:02d}-*-slot-{slot}/disc-paths.log"))
        if not matches:
            continue
        evidence = matches[-1].read_text(encoding="utf-8", errors="replace")
        if expected_stage in evidence:
            recovered[index] = {
                "index": index,
                "gci": gci_path.name,
                "slot": slot,
                "expected_stage": expected_stage,
                "passed": True,
            }
    return recovered


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", required=True, type=Path, help="Legally dumped NTSC-U game image")
    parser.add_argument("--pack", type=Path, default=ROOT / "artifacts/dungeon-pack")
    parser.add_argument("--input-script", type=Path, default=DEFAULT_INPUT_SCRIPT)
    parser.add_argument("--dolphin", type=Path)
    parser.add_argument("--timeout", type=float, default=55.0)
    parser.add_argument("--start", type=int, default=0, help="Zero-based job index to start at")
    parser.add_argument("--limit", type=int, help="Maximum number of checkpoints to run")
    parser.add_argument("--keep-going", action="store_true", help="Continue after a failed stage assertion")
    parser.add_argument("--artifacts", type=Path, default=ROOT / "artifacts/dolphin-pack-validation")
    args = parser.parse_args()

    executable = find_dolphin(args.dolphin)
    if not args.input_script.is_file():
        parser.error(f"input script does not exist: {args.input_script}")
    if args.timeout <= 0 or args.start < 0 or (args.limit is not None and args.limit <= 0):
        parser.error("--timeout and --limit must be positive; --start must not be negative")

    all_jobs = discover_jobs(args.pack)
    jobs = all_jobs[args.start :]
    if args.limit is not None:
        jobs = jobs[: args.limit]
    args.artifacts.mkdir(parents=True, exist_ok=True)
    summary_path = args.artifacts / "summary.json"
    accumulated: dict[int, dict[str, object]] = {}
    if summary_path.is_file():
        existing = json.loads(summary_path.read_text(encoding="utf-8"))
        if not isinstance(existing, list) or not all(isinstance(row, dict) for row in existing):
            raise ValueError(f"invalid existing batch summary: {summary_path}")
        accumulated = {int(row["index"]): row for row in existing}
    accumulated.update(recover_completed_results(args.artifacts, all_jobs))
    if accumulated:
        summary_path.write_text(
            json.dumps([accumulated[key] for key in sorted(accumulated)], indent=2) + "\n",
            encoding="utf-8",
        )
    run_results: list[dict[str, object]] = []

    with tempfile.TemporaryDirectory(prefix="tphd-dolphin-pack-") as directory:
        probe_path = Path(directory) / "probe.gci"
        for index, (gci_path, slot, expected_stage) in enumerate(jobs, args.start):
            probe_path.write_bytes(duplicate_slot(gci_path.read_bytes(), slot))
            validate_inputs(args.game, probe_path, None)
            slug = re.sub(r"[^A-Za-z0-9._-]+", "-", gci_path.stem).strip("-")
            output_dir = args.artifacts / f"{index:02d}-{slug}-slot-{slot}"
            print(f"[{index + 1}] {gci_path.name} slot {slot}: expect {expected_stage}", flush=True)
            result = run_dolphin(
                executable,
                args.game,
                probe_path,
                None,
                args.input_script,
                expected_stage,
                "Null",
                args.timeout,
                output_dir,
            )
            row: dict[str, object] = {
                "index": index,
                "gci": gci_path.name,
                "slot": slot,
                "expected_stage": expected_stage,
                "passed": result == 0,
            }
            run_results.append(row)
            accumulated[index] = row
            summary_path.write_text(
                json.dumps([accumulated[key] for key in sorted(accumulated)], indent=2) + "\n",
                encoding="utf-8",
            )
            if result != 0 and not args.keep_going:
                raise SystemExit(1)

    failures = [result for result in run_results if not result["passed"]]
    print(f"Validated {len(run_results) - len(failures)}/{len(run_results)} checkpoint stage loads")
    raise SystemExit(bool(failures))


if __name__ == "__main__":
    main()
