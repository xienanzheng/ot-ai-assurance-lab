import test from 'node:test';
import assert from 'node:assert/strict';
import { readCatalog } from '../services/web/src/readCatalog.mjs';
test('a transient catalogue failure recovers without a page reload',async()=>{
 let calls=0;
 const rows=await readCatalog(async()=>{if(++calls===1)throw new Error('503');return [{id:'demo'}];},0);
 assert.deepEqual(rows,[{id:'demo'}]);assert.equal(calls,2);
});
test('a persistent catalogue failure terminates and remains reportable',async()=>{
 let calls=0;
 await assert.rejects(readCatalog(async()=>{calls++;throw new Error('unavailable');},0),/unavailable/);
 assert.equal(calls,3);
});
