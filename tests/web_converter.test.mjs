import assert from "node:assert/strict";
import test from "node:test";
import { checksumPair, chooseSlot, detectFormat, gcBody, gcSlotSummary, gciToTphd, profileCoverage, tphdToGci, validateHd, GC_OFFSETS } from "../web/converter.mjs";

function writeU32(data, offset, value) { new DataView(data.buffer).setUint32(offset, value, false); }
function hdFixture(fill = 0x71) { const data = new Uint8Array(0xE00).fill(fill); data.set([0,1],0); const pair=checksumPair(data.subarray(0,-8)); writeU32(data,0xDF8,pair[0]); writeU32(data,0xDFC,pair[1]); return data; }
function gciFixture(fill = 0x41) { const data=new Uint8Array(0x8040).fill(fill); data.set(new TextEncoder().encode("GZ2E01"),0); for(let slot=0;slot<3;slot++){const body=new Uint8Array(0xA8C).fill(fill+slot); const pair=checksumPair(body); data.set(body,GC_OFFSETS[slot]); writeU32(data,GC_OFFSETS[slot]+0xA8C,pair[0]); writeU32(data,GC_OFFSETS[slot]+0xA90,pair[1]);} return data; }

test("TPHD to GCI maps shifted status and keeps a valid target checksum",()=>{const hd=hdFixture(); hd.set([0,20,0,16,1,65],2); const pair=checksumPair(hd.subarray(0,-8)); writeU32(hd,0xDF8,pair[0]); writeU32(hd,0xDFC,pair[1]); const out=tphdToGci(hd,gciFixture(),{slot:1}); assert.deepEqual([...gcBody(out,1).subarray(0,6)],[0,20,0,16,1,65]);});
test("GCI to TPHD maps status, preserves HD-only tail, and validates",()=>{const template=hdFixture(0x63); const gci=gciFixture(); const out=gciToTphd(gci,template,{slot:2,profile:"progress"}); validateHd(out); assert.deepEqual([...out.subarray(2,12)],[...gcBody(gci,2).subarray(0,10)]); assert.deepEqual([...out.subarray(0xA99,0xAA5)],[...template.subarray(0xA99,0xAA5)]);});
test("invalid source checksum is rejected",()=>{const gci=gciFixture(); gci[GC_OFFSETS[0]]^=1; assert.throws(()=>gciToTphd(gci,hdFixture()),/checksum is invalid/);});

// An explicit reference may supply only return place, stage memory, and event
// flags; mapped TPHD inventory must survive, matching tphd_to_gci.py.
test("explicit reference grafts only documented ranges and keeps mapped TPHD inventory",()=>{
  const hd=hdFixture(0x71); hd.set(new Uint8Array(0x30).fill(0x5A),0x09C);
  const pair=checksumPair(hd.subarray(0,-8)); writeU32(hd,0xDF8,pair[0]); writeU32(hd,0xDFC,pair[1]);
  const reference=gciFixture(0x20);
  const out=tphdToGci(hd,gciFixture(0x41),{slot:0,profile:"progress",reference,referenceSlot:0});
  const body=gcBody(out,0), ref=gcBody(reference,0);
  for(const [start,end] of [[0x058,0x064],[0x1F0,0x5F0],[0x7F0,0x8F0]])
    assert.deepEqual([...body.subarray(start,end)],[...ref.subarray(start,end)]);
  // Inventory is TPHD-derived, not silently replaced by the reference.
  assert.deepEqual([...body.subarray(0x09C,0x0CC)],[...hd.subarray(0x09C,0x0CC)]);
  assert.notDeepEqual([...body.subarray(0x09C,0x0CC)],[...ref.subarray(0x09C,0x0CC)]);
});

test("reference mode still honours the profile selector",()=>{
  const hd=hdFixture(0x71); const reference=gciFixture(0x20);
  const safe=gcBody(tphdToGci(hd,gciFixture(0x41),{slot:0,profile:"safe",reference}),0);
  const progress=gcBody(tphdToGci(hd,gciFixture(0x41),{slot:0,profile:"progress",reference}),0);
  assert.notDeepEqual([...safe.subarray(0x09C,0x0CC)],[...progress.subarray(0x09C,0x0CC)]);
});

test("forward conversion never grafts TPHD location structs",()=>{
  const hd=hdFixture(0x71);
  for(const [offset,size] of [[0x040,0x18],[0x058,0x0C],[0x064,0x1C],[0x080,0x1C]]) hd.set(new Uint8Array(size).fill(0xC5),offset);
  const pair=checksumPair(hd.subarray(0,-8)); writeU32(hd,0xDF8,pair[0]); writeU32(hd,0xDFC,pair[1]);
  const template=gciFixture(0x41);
  const body=gcBody(tphdToGci(hd,template,{slot:0,profile:"progress"}),0);
  const templateBody=gcBody(template,0);
  for(const [offset,size] of [[0x040,0x18],[0x058,0x0C],[0x064,0x1C],[0x080,0x1C]])
    assert.deepEqual([...body.subarray(offset,offset+size)],[...templateBody.subarray(offset,offset+size)]);
});

test("reverse conversion keeps every location struct from the HD template",()=>{
  const template=hdFixture(0x63); const gci=gciFixture(0x41);
  const out=gciToTphd(gci,template,{slot:0,profile:"progress"});
  for(const [offset,size] of [[0x040,0x18],[0x058,0x0C],[0x064,0x1C],[0x080,0x1C]])
    assert.deepEqual([...out.subarray(offset,offset+size)],[...template.subarray(offset,offset+size)]);
});

test("format detection distinguishes HD saves, GCIs, and unrelated files", () => {
  assert.equal(detectFormat(hdFixture()), "tphd");
  assert.equal(detectFormat(gciFixture()), "gc");
  assert.equal(detectFormat(new Uint8Array(0x8040)), null, "a GCI-sized blob without the GZ2 game code is not a TP save");
  assert.equal(detectFormat(new Uint8Array(64)), null);
});

test("slot summary reports the player name and ignores checksum-valid empty logs", () => {
  const gci = gciFixture();
  const named = new Uint8Array(gcBody(gci, 1));
  named.fill(0, 0x1B4, 0x1C4);
  named.set(new TextEncoder().encode("LINK"), 0x1B4);
  gci.set(named, GC_OFFSETS[1]);
  const pair = checksumPair(named);
  writeU32(gci, GC_OFFSETS[1] + 0xA8C, pair[0]);
  writeU32(gci, GC_OFFSETS[1] + 0xA90, pair[1]);

  // A zeroed body still checksums cleanly, so only the name marks a real save.
  const blank = new Uint8Array(0xA8C);
  const blankPair = checksumPair(blank);
  gci.set(blank, GC_OFFSETS[2]);
  writeU32(gci, GC_OFFSETS[2] + 0xA8C, blankPair[0]);
  writeU32(gci, GC_OFFSETS[2] + 0xA90, blankPair[1]);

  const summary = gcSlotSummary(gci);
  assert.equal(summary[1].usable, true);
  assert.equal(summary[1].name, "LINK");
  assert.equal(summary[2].usable, false, "an all-zero quest log must not read as populated");
});

test("profile coverage grows with the profile and never counts location structs", () => {
  const [safe, balanced, progress] = ["safe", "balanced", "progress"].map(profileCoverage);
  assert.ok(safe < balanced && balanced < progress);
  assert.ok(safe > 0 && progress < 1, "the destination save always supplies some of the body");
  // player.return_place is load_unsafe and the other location rules are excluded,
  // so no profile may reach the 0x92 bytes they occupy.
  assert.ok(progress * 0xA8C < 0xA8C - 0x92);
});

test("slot choice keeps a usable selection and only moves off an unusable one", () => {
  const summary = [
    { slot: 0, name: "", usable: false },
    { slot: 1, name: "LINK", usable: true },
    { slot: 2, name: "ZELDA", usable: true },
  ];
  // The picker is rebuilt on every profile change; a deliberate choice of quest
  // log 3 must survive it rather than snapping back and patching quest log 2.
  assert.equal(chooseSlot(summary, 2), 2);
  assert.equal(chooseSlot(summary, 1), 1);
  assert.equal(chooseSlot(summary, 0), 1, "an empty slot falls back to the first real save");
  assert.equal(chooseSlot([{ slot: 0, name: "", usable: false }], 0), 0, "with no usable slot the selection stands");
});
