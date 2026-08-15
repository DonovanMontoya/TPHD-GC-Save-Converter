import assert from "node:assert/strict";
import test from "node:test";
import { checksumPair, gcBody, gciToTphd, tphdToGci, validateHd, GC_OFFSETS } from "../web/converter.mjs";

function writeU32(data, offset, value) { new DataView(data.buffer).setUint32(offset, value, false); }
function hdFixture(fill = 0x71) { const data = new Uint8Array(0xE00).fill(fill); data.set([0,1],0); const pair=checksumPair(data.subarray(0,-8)); writeU32(data,0xDF8,pair[0]); writeU32(data,0xDFC,pair[1]); return data; }
function gciFixture(fill = 0x41) { const data=new Uint8Array(0x8040).fill(fill); data.set(new TextEncoder().encode("GZ2E01"),0); for(let slot=0;slot<3;slot++){const body=new Uint8Array(0xA8C).fill(fill+slot); const pair=checksumPair(body); data.set(body,GC_OFFSETS[slot]); writeU32(data,GC_OFFSETS[slot]+0xA8C,pair[0]); writeU32(data,GC_OFFSETS[slot]+0xA90,pair[1]);} return data; }

test("TPHD to GCI maps shifted status and keeps a valid target checksum",()=>{const hd=hdFixture(); hd.set([0,20,0,16,1,65],2); const pair=checksumPair(hd.subarray(0,-8)); writeU32(hd,0xDF8,pair[0]); writeU32(hd,0xDFC,pair[1]); const out=tphdToGci(hd,gciFixture(),{slot:1}); assert.deepEqual([...gcBody(out,1).subarray(0,6)],[0,20,0,16,1,65]);});
test("GCI to TPHD maps status, preserves HD-only tail, and validates",()=>{const template=hdFixture(0x63); const gci=gciFixture(); const out=gciToTphd(gci,template,{slot:2,profile:"progress"}); validateHd(out); assert.deepEqual([...out.subarray(2,12)],[...gcBody(gci,2).subarray(0,10)]); assert.deepEqual([...out.subarray(0xA99,0xAA5)],[...template.subarray(0xA99,0xAA5)]);});
test("invalid source checksum is rejected",()=>{const gci=gciFixture(); gci[GC_OFFSETS[0]]^=1; assert.throws(()=>gciToTphd(gci,hdFixture()),/checksum is invalid/);});
