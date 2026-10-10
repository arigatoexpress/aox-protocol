import test from 'node:test';
import assert from 'node:assert/strict';
import {normalize, makeReceipt, verifyReceipt, MAX_BYTES} from '../../static/csv-core.mjs';
import {referenceOutput} from '../../static/csv-reference.mjs';
const input = csv_text => ({csv_text, columns: ['item_id','quantity']});
const sample = 'item_id,quantity\n bolt_a ,007\nNUT_B,2\n';

test('canonical sample and quoted CRLF round trip', async () => {
  const output = normalize(input(sample));
  assert.equal(output.normalized_csv, 'item_id,quantity\nBOLT_A,7\nNUT_B,2\n');
  assert.deepEqual(output, referenceOutput(input(sample)));
  const quoted = input('"item_id","quantity"\r\n" bolt_a ","007"\r\nNUT_B,2');
  assert.deepEqual(normalize(quoted), output);
  const receipt = await makeReceipt(quoted, 'local_input');
  assert.deepEqual(await verifyReceipt(receipt), output);
});

test('strict structural, quoting, Unicode and formula rejection', () => {
  const invalid = ['', '\ufeff'+sample, 'quantity,item_id\n1,A', 'item_id,item_id\nA,1',
    'item_id,quantity,x\nA,1,2', 'item_id,quantity\n', 'item_id,quantity\n\n',
    'item_id,quantity\nA,1\n\n', 'item_id,quantity\nA,1,2', 'item_id,quantity\nA',
    'item_id,quantity\n"A,1', 'item_id,quantity\nA"B,1', 'item_id,quantity\n"A"x,1',
    'item_id,quantity\rA,1', 'item_id,quantity\n"A\nB",1', 'item_id,quantity\n"A""B",1',
    'item_id,quantity\nA,1\na,2', 'item_id,quantity\nStraße,1', 'item_id,quantity\nＡ,1',
    'item_id,quantity\nA,１２', 'item_id,quantity\nA,1.2', 'item_id,quantity\nA,-1',
    'item_id,quantity\nA,1000001', 'item_id,quantity\nA,00000001',
    ...['=SUM(A1)', '+1', '-1', '@x', '\tA', '\rA', '\u0000A', '\ud800'].map(id => `item_id,quantity\n${id},1`)];
  for (const csv of invalid) {
    assert.throws(() => normalize(input(csv)), undefined, JSON.stringify(csv));
    assert.throws(() => referenceOutput(input(csv)), undefined, JSON.stringify(csv));
  }
});

test('closed input schema and byte/row limits', () => {
  for (const bad of [null, {}, {csv_text:sample, columns:['quantity','item_id']}, {...input(sample), extra:true}, input(42)]) {
    assert.throws(() => normalize(bad));
    assert.throws(() => referenceOutput(bad));
  }
  const hundred = 'item_id,quantity\n'+Array.from({length:100},(_,i)=>`A${i},${i}`).join('\n');
  assert.equal(normalize(input(hundred)).rows.length, 100);
  assert.throws(() => normalize(input(hundred+'\nEXTRA,1')));
  assert.throws(() => referenceOutput(input(hundred+'\nEXTRA,1')));
  for(const text of ['x'.repeat(MAX_BYTES+1),'é'.repeat(MAX_BYTES/2+1)]) {
    assert.throws(() => normalize(input(text)));
    assert.throws(() => referenceOutput(input(text)));
  }
});

test('independent recomputation rejects tampered receipts even with updated hashes', async () => {
  const r = await makeReceipt(input(sample), 'synthetic_sample');
  for (const edit of [r=>r.output.rows[0].quantity=99, r=>r.output.normalized_csv+='EVIL,1\n',
    r=>r.input.csv_text+='EXTRA,1\n', r=>r.input_sha256='0'.repeat(64),
    r=>r.output_sha256='0'.repeat(64), r=>r.kind='real_marketplace', r=>r.extra=true]) {
    const bad = structuredClone(r); edit(bad);
    await assert.rejects(verifyReceipt(bad));
  }
  const bad = structuredClone(r);
  bad.output.rows[0].quantity=99;
  bad.output.normalized_csv=bad.output.normalized_csv.replace('BOLT_A,7','BOLT_A,99');
  bad.output_sha256=await sha(bad.output.normalized_csv);
  await assert.rejects(verifyReceipt(bad));
  // A fully recomputed receipt for different valid input is internally valid, not authenticated.
  assert.equal((await verifyReceipt(await makeReceipt(input(sample.replace('007','008')), 'local_input'))).rows[0].quantity,8);
});
async function sha(text) {return Buffer.from(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text))).toString('hex');}

test('deterministic normalization and reference agree across generated samples', async () => {
  for(let i=0;i<100;i++) {
    const csv=`item_id,quantity\r\n" part_${i} ","00${i}"\r\n`;
    assert.deepEqual(normalize(input(csv)),referenceOutput(input(csv)));
  }
  assert.deepEqual(await makeReceipt(input(sample),'synthetic_sample'),await makeReceipt(input(sample),'synthetic_sample'));
});

test('exact byte boundary and adversarial parser agreement', () => {
  const fixed='item_id,quantity\nA,1\n';
  const text='item_id,quantity\n'+' '.repeat(MAX_BYTES-fixed.length)+'A,1\n';
  assert.equal(new TextEncoder().encode(text).length,MAX_BYTES);
  assert.deepEqual(normalize(input(text)),referenceOutput(input(text)));
  assert.throws(()=>normalize(input(text+' ')));
  // Deterministic short malformed corpus: both parsers must accept/reject consistently.
  const chars=['A','1',',','"','\r','\n',' '];
  let seed=17;
  for(let i=0;i<2000;i++) {
    let body='';
    for(let j=0;j<12;j++){seed=(seed*1664525+1013904223)>>>0;body+=chars[seed%chars.length];}
    const data=input('item_id,quantity\n'+body);
    let a,b;
    try {a=normalize(data);}catch{a=null;}
    try {b=referenceOutput(data);}catch{b=null;}
    assert.deepEqual(a,b,JSON.stringify(body));
  }
});
