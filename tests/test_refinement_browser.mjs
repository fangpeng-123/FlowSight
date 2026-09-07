import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import * as adapter from '../src/flowsight/web/adapter.js';

function browserContext(fetch) {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {
      style: { setProperty() {} }, classList: { contains() { return false; }, toggle() {} },
      addEventListener() {}, querySelector(selector) { return element(`${id}:${selector}`); },
      attributes: {},
      setAttribute(name, value) { this.attributes[name] = value; },
      getAttribute(name) { return this.attributes[name]; },
      innerHTML: '', textContent: '', dataset: {},
    });
    return elements.get(id);
  };
  const context = vm.createContext({
    ...adapter, fetch, console, setTimeout() {},
    window: { addEventListener() {} },
    document: { addEventListener() {}, getElementById: element, documentElement: element('root'),
      querySelector: element, querySelectorAll() { return []; } },
  });
  const source = readFileSync(new URL('../src/flowsight/web/app.js', import.meta.url), 'utf8');
  vm.runInContext(source.replace(/import\s*\{[\s\S]*?\}\s*from\s*"\.\/adapter.js";/, ''), context);
  return context;
}

const graphResponse = () => ({ json: async () => ({ project: {}, nodes: [], edges: [] }) });

test('reindex graph reload invalidates cached ready refinements', async () => {
  const context = browserContext(async () => graphResponse());
  vm.runInContext("refinements.set('pkg/api', {status:'ready', job_id:'old'})", context);
  await vm.runInContext('load()', context);
  assert.equal(vm.runInContext("refinements.has('pkg/api')", context), false);
});

test('a response from before reindex cannot restore an old ready status', async () => {
  let respond;
  const context = browserContext(url => url === '/api/refinements/old'
    ? new Promise(resolve => { respond = resolve; }) : Promise.resolve(graphResponse()));
  vm.runInContext("refinements.set('pkg/api', {status:'pending', job_id:'old'})", context);
  const oldPoll = vm.runInContext("pollRefinement('pkg/api', 'old', 0)", context);
  await vm.runInContext('load()', context);
  respond({ ok: true, json: async () => ({ status: 'ready', job_id: 'old' }) });
  await oldPoll;
  assert.equal(vm.runInContext("refinements.has('pkg/api')", context), false);
});

test('stale artifact offers explicit regeneration and labelled previous output', () => {
  const context = browserContext(async () => graphResponse());
  vm.runInContext("refinements.set('pkg/api', {status:'stale', fallback_artifact_available:true})", context);
  const html = vm.runInContext("deepReadBtn({attrs:{reading_subject:{id:'pkg/api'}}})", context);
  assert.match(html, /Regenerate deep read/);
  assert.match(html, /Stale/);
  assert.match(html, /Open previous deep read/);
});

test('pending deep read shows the truthful waiting state and a cancel action', () => {
  const context = browserContext(async () => graphResponse());
  vm.runInContext("refinements.set('pkg/api', {status:'pending', stage:'waiting_for_agent', job_id:'job-1'})", context);
  const html = vm.runInContext("deepReadBtn({attrs:{reading_subject:{id:'pkg/api'}}})", context);
  assert.match(html, /Waiting for Agent/);
  assert.match(html, /Cancel pending deep read/);
});

test('opening cached ready output rechecks freshness before navigation', async () => {
  const context = browserContext(async () => ({ ok: true, json: async () => ({
    status: 'stale', job_id: 'old', fallback_artifact_available: true,
    fallback_artifact_url: '/api/refinements/old/artifact',
  }) }));
  vm.runInContext("refinements.set('pkg/api', {status:'ready', job_id:'old', artifact_available:true, artifact_url:'/api/refinements/old/artifact'})", context);
  await vm.runInContext("openDeepRead('pkg/api')", context);
  assert.equal(vm.runInContext("refinements.get('pkg/api').status", context), 'stale');
  assert.equal(vm.runInContext("document.getElementById('deep-read-frame').src", context), undefined);
});

test('theme switching updates the structured compact button without replacing it', () => {
  const context = browserContext(async () => graphResponse());
  vm.runInContext("theme = 'light'; applyTheme({ preserveCamera: true })", context);
  assert.equal(
    vm.runInContext("document.getElementById('theme-toggle').querySelector('.tbtn-icon').textContent", context),
    '☀️',
  );
  assert.equal(
    vm.runInContext("document.getElementById('theme-toggle').querySelector('.tbtn-label').textContent", context),
    '亮色',
  );
  assert.equal(
    vm.runInContext("document.getElementById('theme-toggle').getAttribute('aria-label')", context),
    '切换为暗色主题',
  );
});
