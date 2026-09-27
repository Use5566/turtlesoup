const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function harness() {
  const elements = new Map(), intervals = [], calls = [];
  function element(id) {
    if (!elements.has(id)) elements.set(id, {value: '', textContent: '', dataset: {},
      add() {}, replaceChildren() {}, addEventListener() {}, append() {}});
    return elements.get(id);
  }
  const context = vm.createContext({document: {getElementById: element},
    window: {TURTLESOUP_CONFIG: {apiBase: 'https://test.invalid'}, addEventListener() {}},
    location: {hostname: 'localhost'}, Option: function() {}, AbortController,
    setTimeout, clearTimeout, setInterval: (fn, delay) => intervals.push({fn, delay}),
    fetch: async (url, options) => {
      calls.push({url, options});
      return {ok: true, json: async () => url.endsWith('/api/config') ?
        {mode: 'mock', classes: []} : {sync: 'synced'}};
    }});
  vm.runInContext(fs.readFileSync('web/app.js', 'utf8'), context);
  vm.runInContext("token='test'; game={id:'game',state:'active'}", context);
  element('question').value = '尚未送出的草稿';
  element('question-type').value = 'has';
  return {context, elements, intervals, calls};
}

test('35 second autosave posts draft, without submitting an AI question', async () => {
  const h = harness();
  assert.ok(h.intervals.some(x => x.delay === 35000));
  await vm.runInContext('saveDraft()', h.context);
  const request = h.calls.find(x => x.url.endsWith('/save'));
  assert.deepEqual(JSON.parse(request.options.body), {question: '尚未送出的草稿', question_type: 'has'});
  assert.equal(request.options.headers.Authorization, 'Bearer test');
  assert.ok(h.elements.get('sync-status').textContent.includes('已儲存'));
  assert.equal(h.calls.filter(x => x.url.endsWith('/questions')).length, 0);
});

test('failed autosave never claims cloud success and keeps the draft', async () => {
  const h = harness();
  h.context.fetch = async () => {throw new TypeError('offline');};
  await assert.rejects(vm.runInContext('saveDraft()', h.context));
  assert.equal(h.elements.get('question').value, '尚未送出的草稿');
  assert.ok(!h.elements.get('sync-status')?.textContent.includes('已儲存'));
});
