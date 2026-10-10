'use strict';
const $ = id => document.getElementById(id);
let selected = null;
let offerIndex = 0;
function node(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}
function message(text, error = false) {
  $('message').textContent = text;
  $('message').className = error ? 'error' : '';
}
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed.');
  return result;
}
function addOffer(provider = '', price = 10) {
  if ($('offers').children.length >= 8) return;
  const index = ++offerIndex;
  const row = node('div', undefined, 'offer-row');
  for (const [key, title, value] of [['provider', 'Fixture provider', provider], ['price', 'Units', price]]) {
    const field = node('div');
    const label = node('label', title);
    const input = node('input');
    input.id = `${key}-${index}`; label.htmlFor = input.id;
    input.dataset.key = key; input.required = true; input.value = value;
    if (key === 'price') {input.type = 'number'; input.min = 0; input.max = 100; input.step = 1;}
    else input.maxLength = 128;
    field.append(label, input); row.append(field);
  }
  const remove = node('button', '×', 'secondary'); remove.type = 'button';
  remove.setAttribute('aria-label', `Remove offer ${index}`);
  remove.addEventListener('click', () => {row.remove(); $('add-offer').disabled = false;});
  row.append(remove); $('offers').append(row);
  $('add-offer').disabled = $('offers').children.length >= 8;
}
function show(item) {
  selected = item;
  const view = item.view, request = view.request;
  $('result').hidden = false; $('empty').hidden = true;
  $('status').textContent = {passed: 'Known-answer pass', failed: request.verification ? 'Verification failed' : 'Execution failed', unmatched: 'No eligible offer', expired: 'Task expired'}[request.status];
  $('match').textContent = request.match_reason || 'No match explanation recorded.';
  $('candidates').replaceChildren();
  for (const offer of view.offers) {
    const eligible = offer.price <= request.budget && offer.provider !== request.requester;
    const chosen = request.quote?.provider === offer.provider;
    $('candidates').append(node('div', `${offer.provider} · ${offer.price} units · ${chosen ? 'Selected' : eligible ? 'Eligible; lower price or provider ID wins' : 'Excluded: budget or self-match'}`, 'candidate'));
  }
  $('verification').textContent = request.verification
    ? `Schema: ${request.verification.schema_valid ? 'pass' : 'fail'} · Exact uppercase answer: ${request.verification.known_answer_pass ? 'pass' : 'fail'}`
    : (Object.hasOwn(request, 'output')
      ? 'A result was delivered, but no verification verdict was recorded.'
      : 'No delivered result to verify.') + ' No provider quality verdict is inferred. Reason: ' + (request.failure_reason || request.status) + '.';
  $('output').textContent = Object.hasOwn(request, 'output') ? JSON.stringify(request.output, null, 2) : 'No output';
  $('demand').textContent = view.unmet_demand.length ? 'Unmet-demand log · synthetic only: ' + view.unmet_demand[0].reason + '. This is not measured market demand.' : '';
  $('reputation').textContent = `Fixture outcome evidence: ${JSON.stringify(view.fixture_outcomes)}. These are synthetic boolean outcomes, not a reputation score or real-provider evidence.`;
  $('ledger').textContent = JSON.stringify(item.receipt, null, 2);
  message(`Replay valid · ${view.checkpoint.event_count} events · ${item.origin}. Hashes are not signatures.`);
}
async function history() {
  const items = await api('/api/history');
  $('history-list').replaceChildren();
  items.forEach((item, index) => {
    const button = node('button', undefined, 'history-button'); button.type = 'button';
    button.append(node('span', `Receipt ${items.length - index} · ${item.view.request.status} · synthetic`), node('span', `${item.view.checkpoint.event_count} events · ${item.view.checkpoint.final_hash.slice(0, 12)}`));
    button.addEventListener('click', () => show(item)); $('history-list').append(button);
  });
  if (!items.length) $('history-list').append(node('p', 'No receipts yet.', 'hint'));
}
$('task-form').addEventListener('submit', async event => {
  event.preventDefault(); $('run').disabled = true;
  try {
    const offers = [...$('offers').children].map(row => ({provider: row.querySelector('[data-key=provider]').value, price: Number(row.querySelector('[data-key=price]').value)}));
    show(await api('/api/run', {text: $('task-text').value, budget: Number($('budget').value), scenario: $('scenario').value, offers}));
    await history();
  } catch (error) {message(error.message, true);} finally {$('run').disabled = false;}
});
$('add-offer').addEventListener('click', () => addOffer());
$('download').addEventListener('click', () => {
  if (!selected) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(selected.receipt, null, 2)], {type:'application/json'}));
  const link = node('a'); link.href = url; link.download = `aox-synthetic-${selected.view.checkpoint.final_hash.slice(0,12)}.json`;
  link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$('receipt-file').addEventListener('change', async event => {
  const file = event.target.files[0]; if (!file) return;
  try {
    if (file.size > 262144) throw new Error('Receipt exceeds the 256 KiB import limit.');
    show(await api('/api/replay', JSON.parse(await file.text()))); await history();
  } catch (error) {message(error.message, true);} finally {event.target.value = '';}
});
async function init() {
  addOffer('fixture-alpha', 10); addOffer('fixture-beta', 15);
  try {
    await history();
    for (const contract of await api('/api/contracts')) {
      const card = node('article', undefined, 'contract-card');
      card.append(node('span', contract.executable_in_demo ? 'LOCAL TOOL · NO AGENT DISPATCH' : 'SPECIFICATION · NOT EXECUTABLE', 'badge'), node('h3', contract.title), node('code', `${contract.contract_id}@${contract.version}`), node('p', contract.outcome_definition));
      if(contract.executable_in_demo){const link=node('a','Open local CSV tool →');link.href='/csv';card.append(link);}
      const gates = node('ul'); contract.readiness_gates.forEach(gate => gates.append(node('li', gate)));
      card.append(node('h4', 'Before a real pilot'), gates);
      const detail = node('details'), summary = node('summary', 'Inspect schema & acceptance checks');
      detail.append(summary, node('pre', JSON.stringify(contract, null, 2))); card.append(detail); $('contracts').append(card);
    }
  } catch (error) {message(error.message, true);}
}
init();
