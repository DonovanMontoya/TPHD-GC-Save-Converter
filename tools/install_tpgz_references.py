#!/usr/bin/env python3
"""Install hash-pinned raw GC practice saves from the official TPGZ project."""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "references/tpgz-hundo"
COMMIT = "522f6c167996423a7634af53fe5840e30b217fd3"
RAW_ROOT = f"https://raw.githubusercontent.com/zsrtp/tpgz/{COMMIT}"
FILES = {
    "dangoro.bin": "21ff336534abf8a84da0aea87f7bc824b1f4397416bbb76382caa45e26deaebc",
    "fyrus.bin": "9f7b9807224a320fd246c85165291c9cae9cf6ca0c5a3c87de6ce3b390774949",
    "darkhammer.bin": "aac01232d1b0752a2ae927c3ad94ad85de243bc2a7298af823c306799450e8d8",
    "blizzeta.bin": "adc4cd64c643770747c34cd13350f3bf2a41e02944c141dd264460dc61e5dfe6",
    "hc_darknut.bin": "fb4907c595bd70f84bad948a8bd4f867288b233c7f330453223b2be167fab170",
    "post_tot.bin": "a46b90eb3968726546908f695520694bb13affccd9e1c9e1d46e79e4bfe43d77",
    "COPYING.md": "3743f7a4ab5132f7dbeb88e68097657ab8374e74b46b6402efbe80ccfb1b6488",
}
ARMOGOHMA_SHA256 = "fb17a0f972db3299fbd25f4ce77eb385d79e7376b4f294458a602cd0059abacc"


def source_path(name: str) -> str:
    if name == "COPYING.md":
        return name
    return f"res/save_files/hundo/{name}"


def build_armogohma_reference(post_tot: bytes) -> bytes:
    """Turn TPGZ's native post-ToT body into a pre-Armogohma boss-room body."""

    if len(post_tot) != 0xA8C:
        raise ValueError("TPGZ post_tot.bin must be one 0xA8C-byte GC quest-log body")
    body = bytearray(post_tot)
    body[0x058:0x060] = b"D_MN06A\0"
    body[0x060:0x064] = bytes((0, 50, 0x15, 0))

    # Temple of Time is dSv_memory_c index 0x15; mDungeonItem is byte 0x1D
    # of its 0x20-byte memory record. Clear boss-dead, post-boss life, and
    # boss-demo bits while retaining the boss key and native GC inventory.
    temple_dungeon_item = 0x1F0 + 0x15 * 0x20 + 0x1D
    body[temple_dungeon_item] &= ~((1 << 3) | (1 << 4) | (1 << 5))

    # F_0267 (0x2004) is the decomp's "Temple of Time clear" event bit.
    body[0x7F0 + 0x20] &= ~0x04
    return bytes(body)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, expected_sha256 in FILES.items():
        url = f"{RAW_ROOT}/{source_path(name)}"
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read()
        actual_sha256 = hashlib.sha256(data).hexdigest()
        if actual_sha256 != expected_sha256:
            raise RuntimeError(
                f"TPGZ asset hash mismatch for {name}: "
                f"expected {expected_sha256}, got {actual_sha256}"
            )
        (OUTPUT / name).write_bytes(data)
        print(f"Installed {name} ({len(data)} bytes, sha256={actual_sha256})")

    armogohma = build_armogohma_reference((OUTPUT / "post_tot.bin").read_bytes())
    actual_armogohma_sha256 = hashlib.sha256(armogohma).hexdigest()
    if actual_armogohma_sha256 != ARMOGOHMA_SHA256:
        raise RuntimeError(
            "Derived Armogohma reference hash mismatch: "
            f"expected {ARMOGOHMA_SHA256}, got {actual_armogohma_sha256}"
        )
    (OUTPUT / "armogohma-derived.bin").write_bytes(armogohma)
    print(
        "Derived armogohma-derived.bin "
        f"({len(armogohma)} bytes, sha256={actual_armogohma_sha256})"
    )
    print(f"TPGZ references installed under {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
