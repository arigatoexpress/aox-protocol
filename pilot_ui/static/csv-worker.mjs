import {makeReceipt,verifyReceipt} from './csv-core.mjs';
self.onmessage = async ({data}) => {
  try {
    if(data.action==='normalize') {
      const receipt=await makeReceipt(data.input,data.source_kind);
      self.postMessage({receipt,output:receipt.output});
    } else if(data.action==='verify') {
      const output=await verifyReceipt(data.receipt);
      self.postMessage({receipt:data.receipt,output});
    } else throw new Error('Unknown local operation.');
  } catch(error) {self.postMessage({error:error.message});}
};
