import assert from "node:assert/strict";
import test from "node:test";
import { checksumPair, gcBody, gciToTphd, tphdToGci, validateHd, GC_OFFSETS } from "../web/converter.mjs";

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

test("reverse conversion keeps every location struct from the HD template",()=>{
  const template=hdFixture(0x63); const gci=gciFixture(0x41);
  const out=gciToTphd(gci,template,{slot:0,profile:"progress"});
  for(const [offset,size] of [[0x040,0x18],[0x058,0x0C],[0x064,0x1C],[0x080,0x1C]])
    assert.deepEqual([...out.subarray(offset,offset+size)],[...template.subarray(offset,offset+size)]);
});
