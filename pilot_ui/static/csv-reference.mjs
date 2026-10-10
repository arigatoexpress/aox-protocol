/* Independent verifier: complete CSV grammar matching, separate from the producer's
   character state machine and normalization code. No imports from the producer. */
export function referenceOutput(input) {
  const fail = () => {throw new Error('Independent CSV reference check failed.');};
  if (!input || Object.getPrototypeOf(input) !== Object.prototype ||
      Object.keys(input).sort().join(',') !== 'columns,csv_text' ||
      JSON.stringify(input.columns) !== '["item_id","quantity"]' || typeof input.csv_text !== 'string') fail();
  const text = input.csv_text;
  if (!text.length || new TextEncoder().encode(text).length > 32768 || text[0] === '\ufeff' || /[\uD800-\uDFFF]/u.test(text)) fail();
  // Each sticky match consumes one complete field and its delimiter; no skipped bytes.
  const field = /(?:"((?:[^"\r\n]|\r\n|\n|"")*)"|([^",\r\n]*))(,|\r\n|\n|$)/y;
  const records = []; let row = []; let offset = 0;
  while (offset < text.length) {
    field.lastIndex = offset;
    const match = field.exec(text);
    if (!match || match[0].length === 0) fail();
    row.push(match[1] !== undefined ? match[1].replaceAll('""','"') : match[2]);
    offset = field.lastIndex;
    if (match[3] !== ',') {records.push(row); row=[];}
    else if (offset === text.length) {row.push(''); records.push(row); row=[];}
    if(records.length > 101) fail();
  }
  if (row.length) fail();
  if (JSON.stringify(records.shift()) !== '["item_id","quantity"]' || !records.length) fail();
  const rows=[]; const used=new Set();
  for(const cells of records) {
    if(cells.length !== 2) fail();
    const id=cells[0].replace(/^ +| +$/g,'');
    const count=cells[1].replace(/^ +| +$/g,'');
    if(!/^[A-Za-z0-9_][A-Za-z0-9_-]{0,31}$/.test(id) || !/^[0-9]{1,7}$/.test(count)) fail();
    const upper=id.toUpperCase(), quantity=Number(count);
    if(quantity > 1000000 || used.has(upper)) fail();
    used.add(upper); rows.push({item_id:upper,quantity});
  }
  return {rows, normalized_csv:['item_id,quantity',...rows.map(r=>r.item_id+','+r.quantity),''].join('\n')};
}
