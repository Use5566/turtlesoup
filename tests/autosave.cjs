const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function harness() {
  const elements = new Map(), intervals = [], calls = [];
  function element(id) {
    if (!elements.has(id)) elements.set(id, {value: '', textContent: '', dataset: {},
      options: [], add(option) { this.options.push(option); }, replaceChildren(...items) { this.options = items; }, listeners: {}, addEventListener(name, fn) { this.listeners[name] = fn; }, append() {}});
    return elements.get(id);
  }
  const context = vm.createContext({document: {getElementById: element},
    window: {TURTLESOUP_CONFIG: {apiBase: 'https://test.invalid'}, addEventListener() {}},
    location: {hostname: 'localhost'}, Option: function(text, value) {this.text = text; this.value = value;}, AbortController,
    setTimeout, clearTimeout, setInterval: (fn, delay) => intervals.push({fn, delay}),
    fetch: async (url, options) => {
      calls.push({url, options});
      return {ok: true, json: async () => url.endsWith('/api/config') ?
        {mode: 'mock', classes: []} : {sync: 'synced'}};
    }});
  vm.runInContext(fs.readFileSync('web/app.js', 'utf8'), context);
  vm.runInContext("token='test'; game={id:'game',state:'active'}", context);
  element('question').value = '尚未送出的草稿';
  return {context, elements, intervals, calls};
}

test('35 second autosave posts draft, without submitting an AI question', async () => {
  const h = harness();
  assert.ok(h.intervals.some(x => x.delay === 35000));
  await vm.runInContext('saveDraft()', h.context);
  const request = h.calls.find(x => x.url.endsWith('/save'));
  assert.deepEqual(JSON.parse(request.options.body), {question: '尚未送出的草稿'});
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


test('login offers exactly classes 1-7 and seats 1-29', async () => {
  const h = harness();
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(h.elements.get('classroom').options.slice(1).map(o => o.value), Array.from({length:7},(_,i)=>String(i+1)));
  assert.deepEqual(h.elements.get('seat').options.map(o => o.value), Array.from({length:29},(_,i)=>String(i+1)));
});


test('single available puzzle opens directly without a selection card', async () => {
  const h = harness();
  h.context.fetch = async (url, options) => {
    h.calls.push({url, options});
    return {ok:true, json:async () => url.endsWith('/api/activities') ?
      {activities:[{id:'first',title:'臺灣藍鵲'}]} : {id:'saved',draft:'保留草稿'}};
  };
  vm.runInContext('renderGame = () => {}', h.context);
  await vm.runInContext('activities()', h.context);
  assert.equal(h.elements.get('game-view').hidden, false);
  assert.equal(h.elements.get('activities-view').hidden, true);
  assert.equal(h.elements.get('back').hidden, true);
  assert.equal(h.elements.get('question').value, '保留草稿');
  assert.equal(JSON.parse(h.calls.find(c => c.url.endsWith('/api/games')).options.body).activity, 'first');
});


test('logout saves draft before ending login and has no manual finish button', async () => {
  const h = harness();
  await h.elements.get('logout').listeners.click();
  const paths = h.calls.map(c => c.url);
  assert.ok(paths.findIndex(p => p.endsWith('/save')) < paths.findIndex(p => p.endsWith('/api/logout')));
  assert.equal(vm.runInContext('token', h.context), '');
  assert.equal(h.elements.get('login-view').hidden, false);
  assert.ok(!fs.readFileSync('web/index.html','utf8').includes('id="finish"'));
});

test('failed final save keeps login and draft available for retry', async () => {
  const h = harness();
  h.context.fetch = async (url, options) => { h.calls.push({url,options}); throw new TypeError('offline'); };
  await h.elements.get('logout').listeners.click();
  assert.ok(!h.calls.some(c => c.url.endsWith('/api/logout')));
  assert.equal(vm.runInContext('token', h.context), 'test');
  assert.equal(h.elements.get('question').value, '尚未送出的草稿');
});

test('server-saved draft awaiting Sheets sync is shown accurately and allows logout', async () => {
  const h = harness();
  h.context.fetch = async (url, options) => {
    h.calls.push({url, options});
    return {ok: true, json: async () => ({sync: 'pending'})};
  };
  await vm.runInContext('saveDraft()', h.context);
  assert.match(h.elements.get('sync-status').textContent, /已保存至伺服器/);
  assert.match(h.elements.get('sync-status').textContent, /等待同步試算表/);
  assert.ok(!h.elements.get('sync-status').textContent.includes('已儲存至試算表'));
  await h.elements.get('logout').listeners.click();
  assert.ok(h.calls.some(c => c.url.endsWith('/api/logout')));
  assert.equal(vm.runInContext('token', h.context), '');
});
