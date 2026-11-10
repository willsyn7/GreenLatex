// Exercise the shipped inline script with Node's standard library and a small DOM stub.
// These verify UI state changes; they do not emulate a browser's native PDF renderer.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = readFileSync(path.join(__dirname, '../web/preview.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function harness(responses) {
  const nodes = new Map();
  let reloads = 0;
  const viewer = {hidden: true};
  Object.defineProperty(viewer, 'src', {set(value) {this.url = value; reloads++;}});
  nodes.set('#viewer', viewer);
  const timers = [];
  const requests = [];
  const context = vm.createContext({
    location: {pathname: '/test-token/'},
    document: {querySelector(selector) {
      if (!nodes.has(selector)) nodes.set(selector, {style: {}, hidden: true});
      return nodes.get(selector);
    }},
    fetch: async (url, options) => {
      requests.push({url, options});
      const response = responses.shift();
      if (response instanceof Error) throw response;
      return {ok: response.httpOk !== false, json: async () => response};
    },
    setTimeout: (callback, delay) => timers.push({callback, delay}),
  });
  vm.runInContext(script, context);
  return {
    nodes, viewer, requests, timers,
    get reloads() {return reloads;},
    async flush() {await new Promise(resolve => setImmediate(resolve));},
    async next() {timers.shift().callback(); await this.flush();},
  };
}

const success = {source: 'resume.tex', ok: true, building: false,
  message: 'Build succeeded', log: 'Compiler output', revision: 'first'};

test('first successful build displays the PDF and download link', async () => {
  const h = harness([success]); await h.flush();
  assert.equal(h.viewer.hidden, false);
  assert.equal(h.viewer.url, '/test-token/document.pdf?v=first');
  assert.equal(h.nodes.get('#pdf').href, h.viewer.url);
  assert.equal(h.nodes.get('#empty').hidden, true);
  assert.equal(h.nodes.get('#status').textContent, 'Build succeeded');
  assert.equal(h.requests[0].options.cache, 'no-store');
});

test('polling unchanged output does not reload the PDF', async () => {
  const h = harness([success, success]); await h.flush(); await h.next();
  assert.equal(h.reloads, 1);
  assert.equal(h.timers[0].delay, 750);
});

test('new output refreshes the PDF exactly once', async () => {
  const h = harness([success, {...success, revision: 'second'}]);
  await h.flush(); await h.next();
  assert.equal(h.reloads, 2);
  assert.equal(h.viewer.url, '/test-token/document.pdf?v=second');
});

test('compiler failure retains the last good PDF and displays the error', async () => {
  const h = harness([success, {...success, ok: false, message: 'Build failed', log: 'Undefined control sequence'}]);
  await h.flush(); await h.next();
  assert.equal(h.reloads, 1);
  assert.equal(h.viewer.hidden, false);
  assert.equal(h.nodes.get('#status').textContent, 'Build failed');
  assert.equal(h.nodes.get('#log').textContent, 'Undefined control sequence');
});

test('building status is shown without hiding the existing PDF', async () => {
  const h = harness([success, {...success, building: true}]); await h.flush(); await h.next();
  assert.equal(h.nodes.get('#status').textContent, 'Building…');
  assert.equal(h.viewer.hidden, false);
  assert.equal(h.reloads, 1);
});

test('network and HTTP errors keep polling so the preview can recover', async () => {
  for (const error of [new Error('disconnected'), {httpOk: false}]) {
    const h = harness([error, success]); await h.flush();
    assert.match(h.nodes.get('#status').textContent, /disconnected/);
    await h.next();
    assert.equal(h.viewer.hidden, false);
    assert.equal(h.nodes.get('#status').textContent, 'Build succeeded');
  }
});

test('before the first PDF, build errors leave the placeholder visible', async () => {
  const h = harness([{...success, ok: false, revision: null, message: 'Missing package'}]);
  await h.flush();
  assert.equal(h.viewer.hidden, true);
  assert.equal(h.reloads, 0);
  assert.equal(h.nodes.get('#status').textContent, 'Missing package');
});
