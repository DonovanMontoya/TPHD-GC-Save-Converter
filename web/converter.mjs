export const HD_SIZE = 0xE00;
export const GCI_SIZE = 0x8040;
export const GC_BODY_SIZE = 0xA8C;
export const GC_LOG_SIZE = 0xA94;
export const GC_OFFSETS = [0x4048, 0x4ADC, 0x5570];
export const PROFILES = ["safe", "balanced", "progress"];

const RULES = [
  ["player.status_a.max_life", 0x000, 2, 0x002, "copy", "observed"],
  ["player.status_a.life", 0x002, 2, 0x004, "copy", "observed"],
  ["player.status_a.rupees", 0x004, 2, 0x006, "copy", "observed"],
  ["player.status_a.max_oil", 0x006, 2, 0x008, "copy", "observed"],
  ["player.status_a.oil", 0x008, 2, 0x00A, "copy", "observed"],
  ["player.status_a.unknown10", 0x00A, 1, 0x00C, "copy", "observed"],
  ["player.status_a.select_items", 0x00B, 4, 0x00D, "copy", "observed"],
  ["player.status_a.mix_items", 0x00F, 4, 0x011, "copy", "observed"],
  ["player.status_a.equipment", 0x013, 6, 0x015, "copy", "observed"],
  ["player.status_a.wallet_size", 0x019, 1, 0x01B, "copy", "observed"],
  ["player.status_a.magic", 0x01A, 4, 0x01C, "copy", "observed"],
  ["player.status_a.transform_status", 0x01E, 1, 0x020, "copy", "observed"],
  ["player.status_b", 0x028, 0x18, 0x028, "copy", "observed"],
  ["player.horse_place", 0x040, 0x18, 0x040, "copy", "observed"],
  ["player.return_place", 0x058, 0x0C, 0x058, "copy", "load_unsafe"],
  ["player.field_last_stay", 0x064, 0x1C, 0x064, "copy", "observed"],
  ["player.last_mark", 0x080, 0x1C, 0x080, "copy", "observed"],
  ["player.items", 0x09C, 0x30, 0x09C, "copy", "observed"],
  ["player.get_item_flags", 0x0CC, 0x20, 0x0CC, "copy", "observed"],
  ["player.item_record", 0x0EC, 0x0C, 0x0EC, "copy", "observed"],
  ["player.item_max", 0x0F8, 0x08, 0x0F8, "copy", "observed"],
  ["player.collect", 0x100, 0x10, 0x100, "copy", "observed"],
  ["player.wolf", 0x110, 0x04, 0x110, "copy", "observed"],
  ["player.light_drop", 0x114, 0x08, 0x114, "copy", "observed"],
  ["player.letter_info", 0x11C, 0x50, 0x11C, "copy", "observed"],
  ["player.fishing_info", 0x16C, 0x34, 0x16C, "copy", "observed"],
  ["player.info.total_time", 0x1A8, 0x08, 0x1A8, "copy", "observed"],
  ["player.info.death_count", 0x1B2, 0x02, 0x1B2, "copy", "observed"],
  ["player.info.player_name", 0x1B4, 0x10, 0x1B4, "cstring", "observed"],
  ["player.info.horse_name", 0x1C5, 0x10, 0x1C5, "cstring", "observed"],
  ["player.info.clear_count", 0x1D6, 1, 0x1D6, "copy", "observed"],
  ["stage_memory", 0x1F0, 0x400, 0x1F0, "copy", "structural"],
  ["visited_room_memory", 0x5F0, 0x200, 0x5F0, "copy", "structural"],
  ["event_flags", 0x7F0, 0x100, 0x7F0, "copy", "structural"],
  ["minigame_records", 0x940, 0x18, 0x940, "copy", "observed"],
];

// An explicit GC reference may supply only these documented GC-native ranges:
// return place, stage memory, and event flags. Mapped TPHD inventory/status is
// retained, matching apply_gc_state_reference in tphd_to_gci.py.
const REFERENCE_RANGES = [[0x058, 0x064], [0x1F0, 0x5F0], [0x7F0, 0x8F0]];

// Location structs are a mutually consistent bundle with no validated
// cross-version translation in either direction, so they stay native to the
// destination save. Mirrors LOCATION_RULE_NAMES in save_schema.py.
const LOCATION_RULES = new Set([
  "player.horse_place", "player.return_place",
  "player.field_last_stay", "player.last_mark",
]);

// The page derives the conversion direction from the source file itself rather
// than asking: each direction needs exactly one HD save and one GCI, so the
// format of the file being converted fully determines which way it goes.
export function detectFormat(data) {
  if (data.length === HD_SIZE) return "tphd";
  if (data.length === GCI_SIZE && new TextDecoder("ascii").decode(data.subarray(0, 3)) === "GZ2") return "gc";
  return null;
}

// A zeroed quest log still carries a valid checksum, so checksum validity alone
// cannot tell a populated slot from an unused one. The player name does.
export function gcSlotSummary(data) {
  return [0, 1, 2].map((slot) => {
    try {
      const body = gcBody(data, slot);
      let length = 0;
      while (length < 0x10 && body[0x1B4 + length] !== 0) length += 1;
      const name = new TextDecoder("ascii").decode(body.subarray(0x1B4, 0x1B4 + length)).trim();
      return { slot, name, usable: name.length > 0 };
    } catch {
      return { slot, name: "", usable: false };
    }
  });
}

// Which quest log to target given a summary and the currently selected slot.
// A usable selection is always kept, because the picker is re-rendered on every
// option change and must not silently retarget a conversion the user aimed.
export function chooseSlot(summary, current) {
  if (summary[current]?.usable) return current;
  return summary.find((entry) => entry.usable)?.slot ?? current;
}

function referenceOverlap(offset, size) {
  let total = 0;
  for (const [start, end] of REFERENCE_RANGES) {
    total += Math.max(0, Math.min(offset + size, end) - Math.max(offset, start));
  }
  return total;
}

// Share of the GC quest-log body that ends up TPHD-derived; the rest is
// inherited from the destination save. Derived from RULES so the copy on the
// page cannot drift away from the mapping table.
//
// A reference is applied after the mapping rules, so any mapped byte inside
// REFERENCE_RANGES is overwritten and must not be counted as a TPHD
// contribution. Under progress that is stage_memory and event_flags, which is
// most of what the profile appears to transfer.
export function profileCoverage(profile, { reference = false } = {}) {
  assertProfile(profile);
  let mapped = 0;
  for (const [name, gcOffset, size, , , confidence] of RULES) {
    if (LOCATION_RULES.has(name) || !enabled(name, confidence, profile)) continue;
    mapped += reference ? size - referenceOverlap(gcOffset, size) : size;
  }
  return mapped / GC_BODY_SIZE;
}

export function checksumPair(data) {
  let raw = 0;
  for (const value of data) raw += value;
  return [raw >>> 0, (-(raw + data.length)) >>> 0];
}

function readU32(data, offset) {
  return new DataView(data.buffer, data.byteOffset, data.byteLength).getUint32(offset, false);
}

function writeU32(data, offset, value) {
  new DataView(data.buffer, data.byteOffset, data.byteLength).setUint32(offset, value, false);
}

function assertProfile(profile) {
  if (!PROFILES.includes(profile)) throw new Error(`Unknown profile: ${profile}`);
}

export function validateHd(data, label = "TPHD slot") {
  if (data.length !== HD_SIZE) throw new Error(`${label} must be 0xE00 bytes`);
  const expected = checksumPair(data.subarray(0, HD_SIZE - 8));
  if (readU32(data, HD_SIZE - 8) !== expected[0] || readU32(data, HD_SIZE - 4) !== expected[1]) {
    throw new Error(`${label} checksum is invalid`);
  }
}

export function validateGci(data) {
  if (data.length !== GCI_SIZE) throw new Error("GameCube GCI must be 0x8040 bytes");
  const id = new TextDecoder("ascii").decode(data.subarray(0, 6));
  if (!id.startsWith("GZ2")) throw new Error(`Not a Twilight Princess GCI (${id})`);
}

export function gcBody(data, slot) {
  validateGci(data);
  if (![0, 1, 2].includes(slot)) throw new Error("GC slot must be 0, 1, or 2");
  const log = data.subarray(GC_OFFSETS[slot], GC_OFFSETS[slot] + GC_LOG_SIZE);
  const expected = checksumPair(log.subarray(0, GC_BODY_SIZE));
  if (readU32(log, GC_BODY_SIZE) !== expected[0] || readU32(log, GC_BODY_SIZE + 4) !== expected[1]) {
    throw new Error(`GameCube slot ${slot + 1} checksum is invalid`);
  }
  return log.subarray(0, GC_BODY_SIZE);
}

function enabled(name, confidence, profile) {
  if (confidence === "observed") {
    return profile !== "safe" || name.startsWith("player.info.") || name.startsWith("player.status_a.");
  }
  return confidence === "structural" && profile === "progress";
}

function copyCString(destination, dstOffset, source, srcOffset, size) {
  destination.fill(0, dstOffset, dstOffset + size);
  let length = 0;
  while (length < size && source[srcOffset + length] !== 0) length += 1;
  destination.set(source.subarray(srcOffset, srcOffset + length), dstOffset);
}

function applyRule(destination, source, rule, reverse = false) {
  const [, gcOffset, size, hdOffset, strategy] = rule;
  const dst = reverse ? hdOffset : gcOffset;
  const src = reverse ? gcOffset : hdOffset;
  if (strategy === "cstring") copyCString(destination, dst, source, src, size);
  else destination.set(source.subarray(src, src + size), dst);
}

function setEvent(body, flag) { body[0x7F0 + (flag >> 8)] |= flag & 0xFF; }
function normalizeWolf(body, hd) {
  const scent = hd[0x018];
  if (![0xB0, 0xB2, 0xB3, 0xB4, 0xB5].includes(scent)) return;
  body[0x016] = scent;
  body[0x00D] = scent;
  const wordOffset = 0x0CC + Math.floor(scent / 32) * 4;
  writeU32(body, wordOffset, readU32(body, wordOffset) | (1 << (scent % 32)));
  for (const flag of [0x4308, 0x0501, 0x0C10]) setEvent(body, flag);
  if (scent === 0xB0) setEvent(body, 0x2220);
  if (scent === 0xB4) setEvent(body, 0x2240);
}

export function tphdToGci(hd, template, { profile = "safe", slot = 0, reference = null, referenceSlot = 0 } = {}) {
  assertProfile(profile);
  validateHd(hd);
  validateGci(template);
  const output = new Uint8Array(template);
  const body = new Uint8Array(gcBody(template, slot));
  for (const rule of RULES) {
    const [name, , , , , confidence] = rule;
    if (!LOCATION_RULES.has(name) && enabled(name, confidence, profile)) applyRule(body, hd, rule);
  }
  if (reference) {
    const referenceBody = gcBody(reference, referenceSlot);
    for (const [start, end] of REFERENCE_RANGES) body.set(referenceBody.subarray(start, end), start);
  }
  if (profile !== "safe") normalizeWolf(body, hd);
  const offset = GC_OFFSETS[slot];
  output.set(body, offset);
  const [sum, negative] = checksumPair(body);
  writeU32(output, offset + GC_BODY_SIZE, sum);
  writeU32(output, offset + GC_BODY_SIZE + 4, negative);
  gcBody(output, slot);
  return output;
}

export function gciToTphd(gci, template, { profile = "safe", slot = 0 } = {}) {
  assertProfile(profile);
  validateHd(template, "TPHD template");
  const body = gcBody(gci, slot);
  const output = new Uint8Array(template);
  for (const rule of RULES) {
    const [name, , , , , confidence] = rule;
    if (!LOCATION_RULES.has(name) && enabled(name, confidence, profile)) applyRule(output, body, rule, true);
  }
  const [sum, negative] = checksumPair(output.subarray(0, HD_SIZE - 8));
  writeU32(output, HD_SIZE - 8, sum);
  writeU32(output, HD_SIZE - 4, negative);
  validateHd(output, "Converted TPHD slot");
  return output;
}
