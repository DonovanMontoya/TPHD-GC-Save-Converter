#!/usr/bin/env python3
"""Rank GC quest-log references for a TPHD save's scene/progression state."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from tphd_to_gci import (
    GC_GCI_SIZE,
    GC_QUEST_LOG_BODY_SIZE,
    GC_QUEST_LOG_OFFSETS,
    GC_QUEST_LOG_SIZE,
    HD_QUEST_LOG_SIZE,
    checksum_pair,
    c_string,
    stored_checksum_pair,
    validate_hd_slot,
)

IGNORED_REFERENCE_DIRECTORIES = {
    ".git",
    "__pycache__",
    "artifacts",
    "probe-exports",
}


@dataclass(frozen=True)
class ReferenceSlot:
    path: Path
    slot: int
    label: str
    body: bytes
    file_sha256: str = ""


@dataclass(frozen=True)
class CuratedReferenceHint:
    hd_sha256: str
    reference_sha256: str | None
    reference_slot: int | None
    note: str
    unsupported_reason: str | None


@dataclass(frozen=True)
class MatchScore:
    path: str
    slot: int
    label: str
    stage: str
    point: int
    room: int
    total: int
    stage_penalty: int
    event_bits: int
    stage_bits: int
    visited_bits: int
    item_bytes: int
    status_penalty: int


def annotation_file(path: Path) -> Path | None:
    for name in ("List with Annotations.txt", "List of Saves.txt"):
        candidate = path.parent / name
        if candidate.is_file():
            return candidate
    return None


def slot_label(path: Path, slot: int) -> str:
    annotations = annotation_file(path)
    index_match = re.match(r"(\d+)", path.name)
    if annotations is None or index_match is None:
        return ""
    index = index_match.group(1)
    lines = [line.strip() for line in annotations.read_text(errors="replace").splitlines()]
    for line_index, line in enumerate(lines):
        if not (line.startswith(index + " ") or line.startswith(index + ":")):
            continue
        labels: list[str] = []
        for next_line in lines[line_index + 1 :]:
            if not next_line:
                continue
            if re.match(r"\d+(?:\b|:)", next_line):
                break
            labels.append(next_line.removeprefix("-").strip())
            if len(labels) == 3:
                break
        return labels[slot] if slot < len(labels) else ""
    return ""


def load_reference_slots(roots: list[Path]) -> list[ReferenceSlot]:
    references: list[ReferenceSlot] = []
    seen: set[tuple[Path, int]] = set()
    for root in roots:
        paths = [root] if root.is_file() else sorted(
            path
            for path in root.rglob("*")
            if path.suffix.lower() in {".bin", ".gci"}
            if not any(part in IGNORED_REFERENCE_DIRECTORIES for part in path.relative_to(root).parts)
        )
        for path in paths:
            resolved = path.resolve()
            data = path.read_bytes()
            file_sha256 = hashlib.sha256(data).hexdigest()
            if len(data) == GC_QUEST_LOG_BODY_SIZE and path.suffix.lower() == ".bin":
                key = (resolved, 0)
                if key not in seen:
                    references.append(
                        ReferenceSlot(path, 0, path.stem.replace("_", " "), data, file_sha256)
                    )
                    seen.add(key)
                continue
            if len(data) != GC_GCI_SIZE or not data.startswith(b"GZ2"):
                continue
            for slot, offset in enumerate(GC_QUEST_LOG_OFFSETS):
                key = (resolved, slot)
                quest_log = data[offset : offset + GC_QUEST_LOG_SIZE]
                if key in seen or checksum_pair(quest_log[:-8]) != stored_checksum_pair(quest_log):
                    continue
                references.append(
                    ReferenceSlot(
                        path,
                        slot,
                        slot_label(path, slot),
                        quest_log[:GC_QUEST_LOG_BODY_SIZE],
                        file_sha256,
                    )
                )
                seen.add(key)
    return references


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")
    return value


def load_reference_hints(path: Path) -> dict[str, CuratedReferenceHint]:
    """Load source-hash-to-reference mappings with strict schema validation."""

    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("version") != 1:
        raise ValueError("Reference hint manifest must be an object with version 1")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Reference hint manifest entries must be a list")

    hints: dict[str, CuratedReferenceHint] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"Reference hint entry {index} must be an object")
        hd_sha256 = _sha256(entry.get("hd_sha256"), f"entries[{index}].hd_sha256")
        note = entry.get("note", "")
        if not isinstance(note, str):
            raise ValueError(f"entries[{index}].note must be a string")
        unsupported_reason = entry.get("unsupported_reason")
        if unsupported_reason is not None:
            if not isinstance(unsupported_reason, str) or not unsupported_reason:
                raise ValueError(f"entries[{index}].unsupported_reason must be a non-empty string")
            if "reference_sha256" in entry or "reference_slot" in entry:
                raise ValueError(
                    f"entries[{index}] cannot contain both unsupported_reason and reference fields"
                )
            reference_sha256 = None
            reference_slot = None
        else:
            reference_sha256 = _sha256(
                entry.get("reference_sha256"),
                f"entries[{index}].reference_sha256",
            )
            reference_slot = entry.get("reference_slot")
            if reference_slot not in (0, 1, 2):
                raise ValueError(f"entries[{index}].reference_slot must be 0, 1, or 2")
        if hd_sha256 in hints:
            raise ValueError(f"Duplicate TPHD SHA-256 in reference hint manifest: {hd_sha256}")
        hints[hd_sha256] = CuratedReferenceHint(
            hd_sha256,
            reference_sha256,
            reference_slot,
            note,
            unsupported_reason,
        )
    return hints


def differing_bits(left: bytes, right: bytes) -> int:
    if len(left) != len(right):
        raise ValueError("Compared ranges must have equal lengths")
    return sum((a ^ b).bit_count() for a, b in zip(left, right, strict=True))


def differing_bytes(left: bytes, right: bytes) -> int:
    if len(left) != len(right):
        raise ValueError("Compared ranges must have equal lengths")
    return sum(a != b for a, b in zip(left, right, strict=True))


def score_reference(hd: bytes, reference: ReferenceSlot) -> MatchScore:
    body = reference.body
    hd_stage = c_string(hd, 0x058, 8)
    gc_stage = c_string(body, 0x058, 8)
    stage_penalty = 0 if hd_stage == gc_stage else 20_000

    event_bits = differing_bits(hd[0x7F0:0x8F0], body[0x7F0:0x8F0])
    stage_bits = differing_bits(hd[0x1F0:0x5F0], body[0x1F0:0x5F0])
    visited_bits = differing_bits(hd[0x5F0:0x7F0], body[0x5F0:0x7F0])

    # These ranges have been individually load-tested and carry coarse item
    # progression without letting volatile rupee/play-time values dominate.
    item_bytes = differing_bytes(hd[0x09C:0x11C], body[0x09C:0x11C])
    mapped_status_bytes = differing_bytes(hd[0x00D:0x021], body[0x00B:0x01F])
    max_life_delta = abs(int.from_bytes(hd[0x002:0x004], "big") - int.from_bytes(body[0x000:0x002], "big"))
    hd_transform = hd[0x020]
    gc_transform = body[0x01E]
    hd_scent = hd[0x018]
    gc_scent = body[0x016]
    status_penalty = (
        max_life_delta * 40
        + mapped_status_bytes * 20
        + (80 if hd_transform != gc_transform else 0)
        + (50 if hd_scent != gc_scent else 0)
    )

    # Cross-platform event and stage-memory bits are not assumed equivalent.
    # Their distances are deliberately weak tie-breakers: the known paired
    # wooden-sword save proves raw bit similarity can otherwise select an
    # earlier, semantically wrong GC state.
    total = (
        stage_penalty
        + item_bytes * 12
        + status_penalty
        + event_bits
        + stage_bits // 4
        + visited_bits // 4
    )
    return MatchScore(
        path=str(reference.path),
        slot=reference.slot,
        label=reference.label,
        stage=gc_stage,
        point=body[0x060],
        room=body[0x061],
        total=total,
        stage_penalty=stage_penalty,
        event_bits=event_bits,
        stage_bits=stage_bits,
        visited_bits=visited_bits,
        item_bytes=item_bytes,
        status_penalty=status_penalty,
    )


def rank_references(hd: bytes, references: list[ReferenceSlot]) -> list[MatchScore]:
    if len(hd) != HD_QUEST_LOG_SIZE:
        raise ValueError(f"TPHD slot must be 0x{HD_QUEST_LOG_SIZE:x} bytes")
    return sorted((score_reference(hd, reference) for reference in references), key=lambda match: match.total)


def confidence_margin(matches: list[MatchScore]) -> int:
    return matches[1].total - matches[0].total if len(matches) >= 2 else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cemu_slot", type=Path)
    parser.add_argument("reference_roots", nargs="+", type=Path)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    hd = args.cemu_slot.read_bytes()
    validate_hd_slot(hd, str(args.cemu_slot))
    references = load_reference_slots(args.reference_roots)
    if not references:
        raise SystemExit("No valid GC reference slots found")
    matches = rank_references(hd, references)
    if args.json:
        print(
            json.dumps(
                {
                    "margin": confidence_margin(matches),
                    "matches": [asdict(match) for match in matches[: args.limit]],
                },
                indent=2,
            )
        )
        return

    print(f"TPHD stage: {c_string(hd, 0x058, 8)} point={hd[0x060]} room={hd[0x061]}")
    print(f"References: {len(references)}")
    print(f"Top-two margin: {confidence_margin(matches)}")
    for index, match in enumerate(matches[: args.limit], start=1):
        label = f" ({match.label})" if match.label else ""
        print(
            f"{index:2}. score={match.total:6} stage={match.stage:8} point={match.point:3} room={match.room:3} "
            f"events={match.event_bits:3} stage_bits={match.stage_bits:4} "
            f"visited={match.visited_bits:3} items={match.item_bytes:3} "
            f"{match.path} slot {match.slot}{label}"
        )


if __name__ == "__main__":
    main()
