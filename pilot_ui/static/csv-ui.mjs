const $ = id => document.getElementById(id);
const sample='item_id,quantity\n bolt_a ,007\nNUT_B,2\n';
let revision=0, worker=null, timeout=null, selected=null, rawInput=null, sourceKind='synthetic_sample';
const urls=new Set();
function status(text,error=false){$('csv-status').textContent=text;$('csv-status').className=error?'error':'';}
function invalidate(){
  revision++; clearTimeout(timeout);timeout=null; if(worker) worker.terminate(); worker=null;selected=null;
  $('csv-result').hidden=true;$('csv-rows').replaceChildren();$('csv-digests').textContent='';
  $('csv-run').disabled=false;$('csv-cancel').disabled=true;
  for(const url of urls) URL.revokeObjectURL(url);urls.clear();
  return revision;
}
function label(){ $('source-label').textContent=sourceKind==='synthetic_sample'?'Synthetic sample selected.':'Local input selected; no claim of trusted origin.'; }
function display(result, imported){
  selected=result.receipt;$('csv-result').hidden=false;
  if(imported){rawInput=selected.input.csv_text;$('csv-input').value=rawInput;sourceKind='local_input';label();$('csv-file').value='';}
  $('csv-result-label').textContent=imported?'IMPORTED LOCAL RECEIPT · SELF-DECLARED SOURCE':sourceKind==='synthetic_sample'?'SYNTHETIC SAMPLE · ACTUAL LOCAL TRANSFORM':'LOCAL INPUT · ACTUAL LOCAL TRANSFORM';
  $('csv-checks').textContent=`${result.output.rows.length} rows · Schema valid · Independent recomputation agrees · Input/output digests agree`;
  for(const row of result.output.rows){const tr=document.createElement('tr');for(const value of [row.item_id,row.quantity]){const td=document.createElement('td');td.textContent=value;tr.append(td);}$('csv-rows').append(tr);}
  $('csv-digests').textContent=`Input SHA-256: ${selected.input_sha256}\nOutput SHA-256: ${selected.output_sha256}`;
  status(imported?'Receipt is internally consistent. Its origin is not authenticated.':'Local normalization and independent verification passed. Nothing was uploaded or automatically saved.');
}
function execute(data, imported=false){
  const version=invalidate();
  $('csv-cancel').disabled=false;status(imported?'Recomputing receipt locally…':'Normalizing and independently verifying locally…');
  try{worker=new Worker('/csv-worker.mjs',{type:'module'});}catch{status('Browser workers are unavailable; no result generated.',true);$('csv-cancel').disabled=true;return;}
  worker.onmessage=({data:result})=>{
    if(version!==revision)return;
    clearTimeout(timeout);timeout=null;worker.terminate();worker=null;$('csv-cancel').disabled=true;
    if(result.error){status(result.error,true);return;}
    display(result,imported);
  };
  worker.onerror=event=>{event.preventDefault();if(version!==revision)return;invalidate();status('Local worker failed; no result generated.',true);};
  timeout=setTimeout(()=>{if(version!==revision)return;invalidate();status('Local computation exceeded 30 seconds; no result retained.',true);},30000);
  try {worker.postMessage(data);} catch {invalidate();status('Receipt or input is too deeply nested or unsupported; no result generated.',true);}
}
async function readFile(file,limit){
  if(file.size>limit)throw new Error(`File exceeds ${limit.toLocaleString()} bytes.`);
  // Preserve BOM so the contract can reject it; reject invalid UTF-8 rather than repair it.
  return new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(await file.arrayBuffer());
}
$('csv-run').addEventListener('click',()=>execute({action:'normalize',input:{csv_text:rawInput ?? $('csv-input').value,columns:['item_id','quantity']},source_kind:sourceKind}));
$('csv-cancel').addEventListener('click',()=>{invalidate();status('Cancelled. No result retained or downloaded.');});
$('csv-input').addEventListener('input',()=>{invalidate();rawInput=null;sourceKind='local_input';label();$('csv-file').value='';status('Input changed. Normalize again to verify this version.');});
$('csv-file').addEventListener('change',async event=>{
  const file=event.target.files[0];const version=invalidate();rawInput=null;$('csv-input').value='';sourceKind='local_input';label();
  if(!file){status('No file selected.');return;}
  $('csv-cancel').disabled=false;status('Reading file into this tab…');
  try{const text=await readFile(file,32768);if(version!==revision)return;rawInput=text;$('csv-input').value=text;$('csv-cancel').disabled=true;status('Local file loaded. Normalize to validate it.');}
  catch{if(version!==revision)return;$('csv-cancel').disabled=true;status('Unable to read CSV: use valid UTF-8 at most 32 KiB.',true);}
});
$('csv-import').addEventListener('change',async event=>{
  const file=event.target.files[0];const version=invalidate();if(!file)return;
  $('csv-cancel').disabled=false;status('Reading local receipt…');
  try{const raw=await readFile(file,262144);if(version!==revision)return;const receipt=JSON.parse(raw);execute({action:'verify',receipt},true);}
  catch{if(version!==revision)return;invalidate();status('Unable to read receipt: use valid UTF-8 JSON at most 256 KiB.',true);}
  finally{event.target.value='';}
});
$('csv-sample').addEventListener('click',()=>{invalidate();rawInput=null;$('csv-input').value=sample;sourceKind='synthetic_sample';$('csv-file').value='';label();status('Synthetic sample loaded. Normalize to verify.');});
$('csv-clear').addEventListener('click',()=>{invalidate();rawInput=null;$('csv-input').value='';$('csv-file').value='';$('csv-import').value='';sourceKind='local_input';label();status('Cleared tab data. Existing downloaded files are unaffected.');});
function download(content,type,name){
  const url=URL.createObjectURL(new Blob([content],{type}));urls.add(url);
  const link=document.createElement('a');link.href=url;link.download=name;link.click();
  setTimeout(()=>{URL.revokeObjectURL(url);urls.delete(url);},1000);
}
$('csv-download').addEventListener('click',()=>{if(selected)download(selected.output.normalized_csv,'text/csv;charset=utf-8','aox-normalized.csv');});
$('csv-receipt').addEventListener('click',()=>{if(selected)download(JSON.stringify(selected,null,2),'application/json','aox-local-csv-receipt.json');});
window.addEventListener('pagehide',()=>{invalidate();rawInput=null;$('csv-input').value='';$('csv-file').value='';$('csv-import').value='';});
$('csv-input').value=sample;label();
