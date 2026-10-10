import {referenceOutput} from './csv-reference.mjs';
export const MAX_BYTES = 32768;
export const CONTRACT = 'data.csv.normalize@1';
const fail = message => {throw new Error(message);};
function keys(value, expected) {
  return value !== null && Object.getPrototypeOf(value) === Object.prototype &&
    Object.keys(value).sort().join(',') === expected.slice().sort().join(',');
}
function inputSchema(input) {
  if (!keys(input,['csv_text','columns']) || typeof input.csv_text !== 'string' ||
      JSON.stringify(input.columns) !== '["item_id","quantity"]') fail('Expected only csv_text and columns [item_id, quantity].');
  const text=input.csv_text;
  if(!text.length || new TextEncoder().encode(text).length > MAX_BYTES) fail('CSV must be 1–32,768 UTF-8 bytes.');
  if(text[0]==='\ufeff') fail('UTF-8 BOM is not supported; save UTF-8 without BOM.');
  if(/[\uD800-\uDFFF]/u.test(text)) fail('Invalid Unicode text.');
}
export function normalize(input) {
  inputSchema(input);
  const text=input.csv_text, records=[];
  let row=[], value='', mode='start';
  function endField(){row.push(value);value='';mode='start';}
  function endRow(){endField();records.push(row);row=[];if(records.length>101) fail('At most 100 data rows are supported.');}
  for(let i=0;i<text.length;i++) {
    const c=text[i];
    if(mode==='quoted') {
      if(c==='"') {if(text[i+1]==='"'){value+='"';i++;}else mode='closed';}
      else {value+=c;}
      continue;
    }
    if(c===',') {endField();continue;}
    if(c==='\n' || c==='\r') {
      if(c==='\r') {if(text[i+1]!=='\n') fail('Use LF or CRLF record endings.');i++;}
      endRow();continue;
    }
    if(mode==='closed') fail('Unexpected text after a closing quote.');
    if(c==='"') {if(mode!=='start') fail('Quotes must enclose an entire cell.');mode='quoted';}
    else {value+=c;mode='plain';}
  }
  if(mode==='quoted') fail('Unclosed quoted cell.');
  if(mode!=='start' || row.length) endRow();
  if(JSON.stringify(records.shift())!=='["item_id","quantity"]') fail('Header must be exactly item_id,quantity; no duplicates or extra columns.');
  if(!records.length) fail('Provide 1–100 data rows.');
  const rows=[], seen=new Set();
  records.forEach((cells,index)=>{
    if(cells.length!==2) fail(`Data row ${index+1}: expected two cells; blank/ragged rows are rejected.`);
    const id=cells[0].replace(/^ +| +$/g,''), quantityText=cells[1].replace(/^ +| +$/g,'');
    if(!/^[A-Za-z0-9_][A-Za-z0-9_-]{0,31}$/.test(id)) fail(`Data row ${index+1}: item_id must use 1–32 ASCII letters, digits, underscore or hyphen, and cannot start with hyphen. Formula-like values and Unicode IDs are rejected.`);
    if(!/^[0-9]{1,7}$/.test(quantityText) || Number(quantityText)>1000000) fail(`Data row ${index+1}: quantity must be 0–1000000 using 1–7 ASCII digits.`);
    const item_id=id.replace(/[a-z]/g,c=>String.fromCharCode(c.charCodeAt(0)-32));
    if(seen.has(item_id)) fail(`Data row ${index+1}: duplicate normalized item_id.`);
    seen.add(item_id);rows.push({item_id,quantity:Number(quantityText)});
  });
  return {rows,normalized_csv:'item_id,quantity\n'+rows.map(r=>`${r.item_id},${r.quantity}\n`).join('')};
}
async function sha(text) {
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));
  return [...new Uint8Array(bytes)].map(n=>n.toString(16).padStart(2,'0')).join('');
}
export async function makeReceipt(input, source_kind) {
  if(!['synthetic_sample','local_input'].includes(source_kind)) fail('Unknown source label.');
  const output=normalize(input);
  const receipt={format:'aox-local-csv-receipt@1',contract:CONTRACT,kind:'local_transform',source_kind,
    input:structuredClone(input),output,input_sha256:await sha(input.csv_text),output_sha256:await sha(output.normalized_csv)};
  await verifyReceipt(receipt);
  return receipt;
}
export async function verifyReceipt(receipt) {
  if(!keys(receipt,['format','contract','kind','source_kind','input','output','input_sha256','output_sha256']) ||
      receipt.format!=='aox-local-csv-receipt@1' || receipt.contract!==CONTRACT || receipt.kind!=='local_transform' ||
      !['synthetic_sample','local_input'].includes(receipt.source_kind)) fail('Unsupported local CSV receipt.');
  inputSchema(receipt.input);
  const expected=referenceOutput(receipt.input);
  if(!keys(receipt.output,['rows','normalized_csv']) || JSON.stringify(receipt.output.rows)!==JSON.stringify(expected.rows) ||
      receipt.output.normalized_csv!==expected.normalized_csv) fail('Output disagrees with independent recomputation.');
  if(receipt.input_sha256!==await sha(receipt.input.csv_text) || receipt.output_sha256!==await sha(expected.normalized_csv)) fail('Receipt digest mismatch.');
  return expected;
}
