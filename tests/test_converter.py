from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from gc_reference_matcher import (
    ReferenceSlot,
    confidence_margin,
    load_reference_hints,
    load_reference_slots,
    rank_references,
)
from gci_to_tphd import build_tphd_slot, convert_gci_to_tphd
from save_schema import LOCATION_RULE_NAMES
from tphd_to_gci import (
    GC_GCI_SIZE,
    GC_QUEST_LOG_BODY_SIZE,
    GC_QUEST_LOG_OFFSETS,
    GC_QUEST_LOG_SIZE,
    HD_QUEST_LOG_SIZE,
    SlotReport,
    apply_gc_state_reference,
    build_mapped_body,
    checksum_pair,
    convert_cemu_save,
    copy_c_string,
    patch_slot,
    quest_log_body_from_gci,
    stored_checksum_pair,
    validate_gci_template,
    validate_hd_slot,
    verify_gc_slot,
)
from tools.install_tpgz_references import build_armogohma_reference
from tools.dolphin_smoke import controller_config, file_monitor_config, parse_input_script
from tools.dolphin_validate_pack import (
    discover_jobs,
    duplicate_slot,
    recover_completed_results,
    stage_disc_path,
    stage_name,
)


def make_hd_slot(fill: int = 0) -> bytes:
    slot = bytearray([fill] * HD_QUEST_LOG_SIZE)
    slot[0:2] = b"\x00\x01"
    slot[0x002:0x004] = (20).to_bytes(2, "big")
    slot[0x004:0x006] = (16).to_bytes(2, "big")
    slot[0x006:0x008] = (321).to_bytes(2, "big")
    slot[0x018] = 0xB4
    slot[0x1B4:0x1C4] = b"Link\x00" + b"X" * 11
    slot[0x1C5:0x1D5] = b"Epona\x00" + b"Y" * 10
    total, negative = checksum_pair(slot[:-8])
    slot[-8:] = total.to_bytes(4, "big") + negative.to_bytes(4, "big")
    return bytes(slot)


def make_gci(fill: int = 0xA5) -> bytes:
    gci = bytearray([fill] * GC_GCI_SIZE)
    gci[:6] = b"GZ2E01"
    for slot in range(3):
        body = bytes([(fill + slot) & 0xFF] * GC_QUEST_LOG_BODY_SIZE)
        patch_slot(gci, body, slot)
    return bytes(gci)


def with_hd_stage(slot: bytes, stage: bytes, point: int = 0, room: int = 0) -> bytes:
    updated = bytearray(slot)
    updated[0x058:0x060] = stage.ljust(8, b"\x00")
    updated[0x060] = point
    updated[0x061] = room
    total, negative = checksum_pair(updated[:-8])
    updated[-8:] = total.to_bytes(4, "big") + negative.to_bytes(4, "big")
    return bytes(updated)


def reference_body_for_hd(hd: bytes, stage: bytes, fill: int = 0) -> bytes:
    body = bytearray([fill] * GC_QUEST_LOG_BODY_SIZE)
    body[0x058:0x060] = stage.ljust(8, b"\x00")
    body[0x000:0x01F] = hd[0x002:0x021]
    body[0x09C:0x11C] = hd[0x09C:0x11C]
    return bytes(body)


def event_on(body: bytes, event_flag: int) -> bool:
    return bool(body[0x7F0 + (event_flag >> 8)] & (event_flag & 0xFF))


class PrimitiveTests(unittest.TestCase):
    def test_checksum_pair_round_trip(self) -> None:
        body = bytes(range(256)) * 3
        pair = checksum_pair(body)
        quest_log = body + pair[0].to_bytes(4, "big") + pair[1].to_bytes(4, "big")
        self.assertEqual(stored_checksum_pair(quest_log), pair)

    def test_copy_c_string_clears_destination_tail(self) -> None:
        destination = bytearray(b"?" * 12)
        copy_c_string(destination, 2, b"A\x00ignored", 0, 8)
        self.assertEqual(destination, b"??A" + b"\x00" * 7 + b"??")

    def test_hd_validation_rejects_size_and_checksum(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be 0xE00"):
            validate_hd_slot(b"short", "fixture")
        corrupt = bytearray(make_hd_slot())
        corrupt[10] ^= 1
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            validate_hd_slot(bytes(corrupt), "fixture")

    def test_gci_validation_rejects_wrong_game_and_size(self) -> None:
        with self.assertRaisesRegex(ValueError, "0x8040"):
            validate_gci_template(b"short")
        wrong_game = bytearray(make_gci())
        wrong_game[:6] = b"NOPE01"
        with self.assertRaisesRegex(ValueError, "Twilight Princess"):
            validate_gci_template(bytes(wrong_game))


class ProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.hd = make_hd_slot(0x11)
        self.template = make_gci(0xA0)
        offset = GC_QUEST_LOG_OFFSETS[0]
        self.template_log = self.template[offset : offset + GC_QUEST_LOG_SIZE]

    def build(self, profile: str, reference: bytes | None = None) -> bytes:
        return build_mapped_body(self.hd, self.template_log, 0, 0, profile, reference)[0]

    def test_safe_maps_shifted_status_and_names_only(self) -> None:
        body = self.build("safe")
        self.assertEqual(body[0:10], self.hd[2:12])
        self.assertEqual(body[0x1B4:0x1B9], b"Link\x00")
        self.assertEqual(body[0x1C5:0x1CB], b"Epona\x00")
        self.assertEqual(body[0x09C], 0xA0)
        self.assertEqual(body[0x1F0], 0xA0)

    def test_balanced_maps_inventory_but_keeps_unsafe_return_place(self) -> None:
        body = self.build("balanced")
        self.assertEqual(body[0x09C:0x0CC], self.hd[0x09C:0x0CC])
        self.assertEqual(body[0x058:0x064], bytes([0xA0]) * 12)
        self.assertEqual(body[0x1F0], 0xA0)

    def test_forward_never_grafts_tphd_location_structs(self) -> None:
        """Location is a coherent bundle; partial TPHD grafting is unvalidated."""
        hd = bytearray(make_hd_slot(0x11))
        for offset, size in ((0x040, 0x18), (0x058, 0x0C), (0x064, 0x1C), (0x080, 0x1C)):
            hd[offset : offset + size] = bytes([0xC5]) * size
        template = make_gci(0x40)
        quest_log = template[GC_QUEST_LOG_OFFSETS[0] : GC_QUEST_LOG_OFFSETS[0] + GC_QUEST_LOG_SIZE]
        for profile in ("safe", "balanced", "progress"):
            body, report = build_mapped_body(bytes(hd), quest_log, 0, 0, profile)
            for offset, size in ((0x040, 0x18), (0x058, 0x0C), (0x064, 0x1C), (0x080, 0x1C)):
                self.assertEqual(
                    body[offset : offset + size],
                    quest_log[offset : offset + size],
                    f"{profile} grafted TPHD location bytes at {offset:#x}",
                )
            self.assertFalse({field.name for field in report.fields} & LOCATION_RULE_NAMES)

    def test_progress_maps_structural_ranges(self) -> None:
        hd_without_scent = bytearray(self.hd)
        hd_without_scent[0x018] = 0
        body = build_mapped_body(bytes(hd_without_scent), self.template_log, 0, 0, "progress")[0]
        self.assertEqual(body[0x1F0:0x5F0], hd_without_scent[0x1F0:0x5F0])
        self.assertEqual(body[0x5F0:0x7F0], hd_without_scent[0x5F0:0x7F0])
        self.assertEqual(body[0x7F0:0x8F0], hd_without_scent[0x7F0:0x8F0])

    def test_wolf_normalization_runs_after_reference_graft(self) -> None:
        reference = bytes([0] * GC_QUEST_LOG_BODY_SIZE)
        body = self.build("progress", reference)
        self.assertEqual(body[0x016], 0xB4)
        self.assertEqual(body[0x00D], 0xB4)
        self.assertTrue(event_on(body, 0x4308))
        self.assertTrue(event_on(body, 0x0501))
        self.assertTrue(event_on(body, 0x0C10))
        self.assertTrue(event_on(body, 0x2240))

    def test_reference_replaces_only_documented_scene_ranges(self) -> None:
        body = bytearray([0x10] * GC_QUEST_LOG_BODY_SIZE)
        reference = bytes([0x20] * GC_QUEST_LOG_BODY_SIZE)
        report = SlotReport(0, 0, "", "", 0, 0, 0)
        apply_gc_state_reference(body, reference, report)
        self.assertEqual(body[0x058:0x064], bytes([0x20]) * 12)
        self.assertEqual(body[0x1F0:0x5F0], bytes([0x20]) * 0x400)
        self.assertEqual(body[0x7F0:0x8F0], bytes([0x20]) * 0x100)
        self.assertEqual(body[0x064], 0x10)
        self.assertEqual(body[0x5F0], 0x10)
        self.assertEqual(body[0x8F0], 0x10)

    def test_unknown_profile_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown conversion profile"):
            self.build("reckless")


class GciTests(unittest.TestCase):
    def test_patch_updates_only_selected_slot_and_checksum(self) -> None:
        original = make_gci()
        patched = bytearray(original)
        body = bytes([0x5A] * GC_QUEST_LOG_BODY_SIZE)
        patch_slot(patched, body, 1)
        self.assertTrue(verify_gc_slot(patched, 1))
        self.assertEqual(patched[GC_QUEST_LOG_OFFSETS[0] : GC_QUEST_LOG_OFFSETS[1]], original[GC_QUEST_LOG_OFFSETS[0] : GC_QUEST_LOG_OFFSETS[1]])
        self.assertEqual(patched[GC_QUEST_LOG_OFFSETS[1] : GC_QUEST_LOG_OFFSETS[1] + GC_QUEST_LOG_BODY_SIZE], body)

    def test_reference_reader_validates_wrapper_and_checksum(self) -> None:
        gci = make_gci()
        self.assertEqual(len(quest_log_body_from_gci(gci, 0)), GC_QUEST_LOG_BODY_SIZE)
        corrupt = bytearray(gci)
        corrupt[GC_QUEST_LOG_OFFSETS[0]] ^= 1
        with self.assertRaisesRegex(ValueError, "checksum is invalid"):
            quest_log_body_from_gci(bytes(corrupt), 0)

    def test_end_to_end_conversion_preserves_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hd_path = root / "ZTP00.dat"
            template_path = root / "template.gci"
            output_path = root / "output.gci"
            hd_path.write_bytes(make_hd_slot())
            template = make_gci()
            template_path.write_bytes(template)
            reports = convert_cemu_save(hd_path, template_path, output_path, None, "safe")
            output = output_path.read_bytes()
            self.assertEqual(len(reports), 1)
            self.assertEqual(len(output), GC_GCI_SIZE)
            self.assertTrue(verify_gc_slot(output, 0))
            self.assertEqual(output[: GC_QUEST_LOG_OFFSETS[0]], template[: GC_QUEST_LOG_OFFSETS[0]])
            self.assertEqual(output[GC_QUEST_LOG_OFFSETS[1] :], template[GC_QUEST_LOG_OFFSETS[1] :])


class ReverseConversionTests(unittest.TestCase):
    def test_safe_reverse_maps_shifted_status_and_preserves_hd_only_bytes(self) -> None:
        gci = make_gci(0x40)
        body = bytearray(quest_log_body_from_gci(gci, 0))
        body[0x000:0x00A] = bytes(range(10))
        body[0x1B4:0x1C4] = b"Hero\0" + b"G" * 11
        template = make_hd_slot(0x77)
        converted, report = build_tphd_slot(bytes(body), template, 0, "safe")
        self.assertEqual(converted[0x002:0x00C], bytes(range(10)))
        self.assertEqual(converted[0x1B4:0x1B9], b"Hero\0")
        self.assertEqual(converted[0xA99:0xAA5], template[0xA99:0xAA5])
        self.assertEqual(converted[0x058:0x064], template[0x058:0x064])
        self.assertTrue(any(field.status == "experimental" for field in report.fields))
        validate_hd_slot(converted, "reverse")

    def test_progress_reverse_maps_structural_blocks(self) -> None:
        body = bytearray(quest_log_body_from_gci(make_gci(), 0))
        body[0x1F0:0x5F0] = bytes([0x31]) * 0x400
        body[0x5F0:0x7F0] = bytes([0x52]) * 0x200
        body[0x7F0:0x8F0] = bytes([0x73]) * 0x100
        converted, _report = build_tphd_slot(bytes(body), make_hd_slot(), 0, "progress")
        self.assertEqual(converted[0x1F0:0x5F0], body[0x1F0:0x5F0])
        self.assertEqual(converted[0x5F0:0x7F0], body[0x5F0:0x7F0])
        self.assertEqual(converted[0x7F0:0x8F0], body[0x7F0:0x8F0])

    def test_reverse_end_to_end_rejects_bad_gci_and_writes_valid_slot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gci_path = root / "input.gci"
            template_path = root / "ZTP00-template.dat"
            output_path = root / "ZTP00.dat"
            gci_path.write_bytes(make_gci())
            template_path.write_bytes(make_hd_slot())
            convert_gci_to_tphd(gci_path, template_path, output_path, 1, "balanced")
            validate_hd_slot(output_path.read_bytes(), "output")
            corrupt = bytearray(make_gci())
            corrupt[GC_QUEST_LOG_OFFSETS[1]] ^= 1
            gci_path.write_bytes(corrupt)
            with self.assertRaisesRegex(ValueError, "checksum is invalid"):
                convert_gci_to_tphd(gci_path, template_path, output_path, 1, "safe")


    def test_reverse_keeps_every_location_struct_from_the_hd_template(self) -> None:
        """Cross-version location translation is unvalidated in reverse."""
        body = bytearray(quest_log_body_from_gci(make_gci(), 0))
        for offset, size in ((0x040, 0x18), (0x058, 0x0C), (0x064, 0x1C), (0x080, 0x1C)):
            body[offset : offset + size] = bytes([0xC5]) * size
        template = make_hd_slot(0x77)
        for profile in ("safe", "balanced", "progress"):
            converted, report = build_tphd_slot(bytes(body), template, 0, profile)
            for offset, size in ((0x040, 0x18), (0x058, 0x0C), (0x064, 0x1C), (0x080, 0x1C)):
                self.assertEqual(
                    converted[offset : offset + size],
                    template[offset : offset + size],
                    f"{profile} overwrote HD location bytes at {offset:#x}",
                )
            mapped = {field.name for field in report.fields}
            self.assertFalse(mapped & LOCATION_RULE_NAMES)


class AutomaticReferenceTests(unittest.TestCase):
    def test_armogohma_derivation_changes_only_documented_gc_fields(self) -> None:
        post_tot = bytearray([0xFF] * GC_QUEST_LOG_BODY_SIZE)
        derived = build_armogohma_reference(bytes(post_tot))
        changed = {index for index, pair in enumerate(zip(post_tot, derived, strict=True)) if pair[0] != pair[1]}
        allowed = set(range(0x058, 0x064)) | {0x4AD, 0x810}
        self.assertEqual(changed, allowed)
        self.assertEqual(derived[0x058:0x064], b"D_MN06A\x00\x002\x15\x00")
        self.assertEqual(derived[0x4AD], 0xC7)
        self.assertEqual(derived[0x810], 0xFB)

    def test_hint_manifest_rejects_conflicting_supported_and_unsupported_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hints.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "entries": [
                            {
                                "hd_sha256": "a" * 64,
                                "unsupported_reason": "missing checkpoint",
                                "reference_sha256": "b" * 64,
                                "reference_slot": 0,
                            }
                        ],
                    }
                )
            )
            with self.assertRaisesRegex(ValueError, "both unsupported_reason and reference fields"):
                load_reference_hints(path)

    def test_recursive_reference_scan_ignores_generated_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "references"
            generated = root / "artifacts" / "exports"
            source.mkdir()
            generated.mkdir(parents=True)
            (source / "source.gci").write_bytes(make_gci())
            (generated / "generated.gci").write_bytes(make_gci())
            references = load_reference_slots([root])
            self.assertEqual({reference.path.name for reference in references}, {"source.gci"})

    def test_raw_tpgz_quest_log_body_is_a_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "darkhammer.bin"
            body = bytes([0x5A]) * GC_QUEST_LOG_BODY_SIZE
            path.write_bytes(body)
            references = load_reference_slots([path])
            self.assertEqual(len(references), 1)
            self.assertEqual(references[0].body, body)
            self.assertEqual(references[0].slot, 0)
            self.assertEqual(references[0].label, "darkhammer")
            self.assertEqual(references[0].file_sha256, hashlib.sha256(body).hexdigest())

    def test_ranker_prefers_exact_stage_and_mapped_progress(self) -> None:
        hd = with_hd_stage(make_hd_slot(0x11), b"D_MN05", point=0, room=22)
        close = ReferenceSlot(Path("close.gci"), 0, "close", reference_body_for_hd(hd, b"D_MN05"))
        far_body = bytearray(reference_body_for_hd(hd, b"D_MN05", 0xFF))
        far = ReferenceSlot(Path("far.gci"), 0, "far", bytes(far_body))
        wrong_stage = ReferenceSlot(Path("wrong.gci"), 0, "wrong", reference_body_for_hd(hd, b"F_SP00"))
        matches = rank_references(hd, [far, wrong_stage, close])
        self.assertEqual(matches[0].path, "close.gci")
        self.assertEqual(matches[0].stage, "D_MN05")
        self.assertGreater(confidence_margin(matches), 0)

    def test_end_to_end_auto_reference_grafts_selected_scene(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hd = with_hd_stage(make_hd_slot(0x11), b"D_MN05", point=0, room=22)
            selected_body = bytearray(reference_body_for_hd(hd, b"D_MN05"))
            selected_body[0x028:0x09C] = bytes([0x69]) * 0x74
            selected_body[0x058:0x060] = b"D_MN05\x00\x00"
            selected_body[0x060:0x064] = b"\x05\x06\x15\x00"
            selected_body[0x1F0:0x5F0] = bytes([0x3C]) * 0x400
            selected_body[0x5F0:0x7F0] = bytes([0xA5]) * 0x200
            selected_body[0x7F0:0x8F0] = bytes([0xC3]) * 0x100
            reference = bytearray(make_gci())
            patch_slot(reference, bytes(selected_body), 0)
            hd_path = root / "ZTP00.dat"
            template_path = root / "template.gci"
            reference_path = root / "references.gci"
            output_path = root / "output.gci"
            hd_path.write_bytes(hd)
            template_path.write_bytes(make_gci())
            reference_path.write_bytes(reference)

            reports = convert_cemu_save(
                hd_path,
                template_path,
                output_path,
                None,
                "progress",
                auto_gc_state_reference_roots=[reference_path],
                auto_reference_min_margin=1,
            )
            output_body = quest_log_body_from_gci(output_path.read_bytes(), 0)
            self.assertEqual(output_body[0x09C:0x1A8], selected_body[0x09C:0x1A8])
            self.assertEqual(output_body[0x028:0x058], selected_body[0x028:0x058])
            self.assertEqual(output_body[0x058:0x064], selected_body[0x058:0x064])
            self.assertEqual(output_body[0x1F0:0x5F0], selected_body[0x1F0:0x5F0])
            self.assertEqual(output_body[0x5F0:0x7F0], selected_body[0x5F0:0x7F0])
            self.assertEqual(output_body[0x8F0:0xA8C], selected_body[0x8F0:0xA8C])
            self.assertEqual(output_body[0:6], hd[2:8])
            self.assertTrue(any("automatically selected" in field.detail for field in reports[0].fields))

    def test_curated_hash_hint_can_select_intentional_different_stage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hd = with_hd_stage(make_hd_slot(0x11), b"F_SP108", point=200, room=6)
            selected_body = bytearray(reference_body_for_hd(hd, b"D_MN05A"))
            selected_body[0x060:0x064] = b"\x01\x32\x15\x00"
            reference = bytearray(make_gci())
            patch_slot(reference, bytes(selected_body), 2)
            reference_bytes = bytes(reference)
            hd_path = root / "ZTP00.dat"
            template_path = root / "template.gci"
            reference_path = root / "references.gci"
            hints_path = root / "hints.json"
            output_path = root / "output.gci"
            hd_path.write_bytes(hd)
            template_path.write_bytes(make_gci())
            reference_path.write_bytes(reference_bytes)
            hints_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "entries": [
                            {
                                "hd_sha256": hashlib.sha256(hd).hexdigest(),
                                "reference_sha256": hashlib.sha256(reference_bytes).hexdigest(),
                                "reference_slot": 2,
                                "note": "curated boss milestone",
                            }
                        ],
                    }
                )
            )

            reports = convert_cemu_save(
                hd_path,
                template_path,
                output_path,
                None,
                "safe",
                auto_gc_state_reference_roots=[reference_path],
                auto_reference_hints=hints_path,
            )
            output_body = quest_log_body_from_gci(output_path.read_bytes(), 0)
            self.assertEqual(output_body[0x058:0x064], selected_body[0x058:0x064])
            self.assertTrue(any("curated boss milestone" in field.detail for field in reports[0].fields))

    def test_curated_unsupported_hint_rejects_known_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hd = with_hd_stage(make_hd_slot(), b"F_SP110")
            hd_path = root / "ZTP00.dat"
            template_path = root / "template.gci"
            reference_path = root / "references.gci"
            hints_path = root / "hints.json"
            hd_path.write_bytes(hd)
            template_path.write_bytes(make_gci())
            reference_path.write_bytes(make_gci())
            hints_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "entries": [
                            {
                                "hd_sha256": hashlib.sha256(hd).hexdigest(),
                                "unsupported_reason": "no GC mid-boss reference",
                            }
                        ],
                    }
                )
            )
            with self.assertRaisesRegex(ValueError, "no GC mid-boss reference"):
                convert_cemu_save(
                    hd_path,
                    template_path,
                    root / "output.gci",
                    None,
                    "safe",
                    auto_gc_state_reference_roots=[reference_path],
                    auto_reference_hints=hints_path,
                )

    def test_auto_reference_rejects_missing_stage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hd_path = root / "ZTP00.dat"
            template_path = root / "template.gci"
            reference_path = root / "references.gci"
            hd_path.write_bytes(with_hd_stage(make_hd_slot(), b"D_MN05"))
            template_path.write_bytes(make_gci())
            reference_path.write_bytes(make_gci())
            with self.assertRaisesRegex(ValueError, "No exact-stage"):
                convert_cemu_save(
                    hd_path,
                    template_path,
                    root / "output.gci",
                    None,
                    "progress",
                    auto_gc_state_reference_roots=[reference_path],
                )


class DolphinHarnessTests(unittest.TestCase):
    def test_batch_probe_duplicates_selected_checkpoint_into_every_slot(self) -> None:
        gci = make_gci(0x40)
        probe = duplicate_slot(gci, 2)
        expected = quest_log_body_from_gci(gci, 2)
        self.assertTrue(all(quest_log_body_from_gci(probe, slot) == expected for slot in range(3)))

    def test_batch_stage_name_reads_and_validates_return_place(self) -> None:
        body = bytearray([0] * GC_QUEST_LOG_BODY_SIZE)
        body[0x058:0x060] = b"D_MN06A\0"
        self.assertEqual(stage_name(bytes(body)), "D_MN06A")
        body[0x058:0x060] = b"bad-name"
        with self.assertRaisesRegex(ValueError, "invalid return-place stage"):
            stage_name(bytes(body))

    def test_batch_stage_assertion_requires_a_complete_path_segment(self) -> None:
        """D_MN06 and D_MN06A are distinct checkpoints, not a substring match."""
        evidence = "W[FileMon]:  123 kB res/Stage/D_MN06A/STG_00.arc\n"
        self.assertIn(stage_disc_path("D_MN06A"), evidence)
        self.assertNotIn(stage_disc_path("D_MN06"), evidence)
        self.assertIn(stage_disc_path("D_MN06"), "res/Stage/D_MN06/R00_00.arc")

    def test_batch_job_discovery_is_stable_and_slot_ordered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = Path(directory)
            for name in ("b.gci", "a.gci"):
                gci = bytearray(make_gci())
                for slot in range(3):
                    body = bytearray(quest_log_body_from_gci(gci, slot))
                    body[0x058:0x060] = f"D_MN0{slot}".encode().ljust(8, b"\0")
                    patch_slot(gci, body, slot)
                (pack / name).write_bytes(gci)
            jobs = discover_jobs(pack)
            self.assertEqual([(path.name, slot) for path, slot, _stage in jobs], [
                ("a.gci", 0), ("a.gci", 1), ("a.gci", 2),
                ("b.gci", 0), ("b.gci", 1), ("b.gci", 2),
            ])

    def test_batch_summary_recovers_from_per_run_disc_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = root / "artifacts"
            result = artifacts / "00-example-slot-0"
            result.mkdir(parents=True)
            (result / "disc-paths.log").write_text("res/Stage/D_MN05/STG_00.arc\n")
            jobs = [(root / "example.gci", 0, "D_MN05")]
            recovered = recover_completed_results(artifacts, jobs)
            self.assertTrue(recovered[0]["passed"])
            self.assertEqual(recovered[0]["expected_stage"], "D_MN05")

    def test_pipe_controller_config_maps_required_gamecube_controls(self) -> None:
        config = controller_config()
        self.assertIn("Device = Pipe/0/tp-controller", config)
        for button in ("A", "B", "X", "Y", "Z", "Start"):
            self.assertIn(f"Buttons/{button} =", config)
        for direction in ("Up", "Down", "Left", "Right"):
            self.assertIn(f"D-Pad/{direction} =", config)

    def test_pipe_input_script_parses_comments_and_absolute_times(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "load.txt"
            script.write_text(
                "# Title input\n0 PRESS START\n0.08 RELEASE START\n1.5 SET MAIN 0 -1\n"
            )
            self.assertEqual(
                parse_input_script(script),
                [(0.0, "PRESS START"), (0.08, "RELEASE START"), (1.5, "SET MAIN 0 -1")],
            )

    def test_file_monitor_config_is_file_only_and_enables_disc_paths(self) -> None:
        config = file_monitor_config()
        self.assertIn("WriteToFile = True", config)
        self.assertIn("WriteToConsole = False", config)
        self.assertIn("FileMon = True", config)

    def test_pipe_input_script_rejects_invalid_or_unsorted_commands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "bad.txt"
            script.write_text("1 PRESS A\n0 RELEASE A\n")
            with self.assertRaisesRegex(ValueError, "timestamps must be nondecreasing"):
                parse_input_script(script)
            script.write_text("0 PRESS POWER\n")
            with self.assertRaisesRegex(ValueError, "unsupported pipe command"):
                parse_input_script(script)


if __name__ == "__main__":
    unittest.main()
