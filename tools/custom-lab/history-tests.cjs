const assert = require('node:assert/strict');
const fs = require('node:fs');

(async () => {
  const source = fs.readFileSync('frontend/static/js/customizer-3d/history-manager.js', 'utf8');
  const { HistoryManager } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
  let restored, fail = false;
  const history = new HistoryManager({ limit: 3, restore: async state => { if (fail && state.value === 2) throw Error('load failed'); restored = state; } });
  const state = value => ({ value, source: { dataUrl: 'data:image/png;base64,shared' } });
  history.clear(state(0));
  for (const value of [1, 2, 3, 4]) history.push(state(value));
  assert.equal(history.states.length, 4); assert.equal(history.assets.size, 1);
  await history.undo(); assert.deepEqual(restored, state(3));
  fail = true;
  await assert.rejects(history.undo(), /load failed/);
  assert.deepEqual(restored, state(3)); assert.equal(history.index, 2); assert.equal(history.busy, false);
  fail = false; await history.undo(); assert.deepEqual(restored, state(2));
  await history.redo(); assert.deepEqual(restored, state(3));
  history.push(state(7)); assert.equal(history.canRedo(), false);
  history.push(state(8), { mergeKey: 'text' }); history.push(state(9), { mergeKey: 'text' });
  await history.undo(); assert.deepEqual(restored, state(7));
  history.clear({ value: 0 }); assert.equal(history.assets.size, 0); assert.equal(history.canUndo(), false);
  console.log('PASS history: bounded snapshots, shared assets, undo/redo, branch replacement, merged typing, failure rollback');
})().catch(error => { console.error(error); process.exitCode = 1; });
