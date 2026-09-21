// Serializable editor states; image data is interned once across the bounded stack.
export class HistoryManager {
  constructor({ restore, limit = 60, onChange = () => {} } = {}) {
    this.restore = restore; this.limit = limit; this.onChange = onChange;
    this.states = []; this.index = -1; this.busy = false; this.assets = new Map();
    this.assetIds = new Map(); this.nextAsset = 0; this.lastKey = ''; this.lastTime = 0;
  }
  canUndo() { return !this.busy && this.index > 0; }
  canRedo() { return !this.busy && this.index < this.states.length - 1; }
  encode(state) {
    return JSON.stringify(state, (key, value) => {
      if (key !== 'dataUrl' || typeof value !== 'string' || !value.startsWith('data:')) return value;
      if (!this.assetIds.has(value)) { const id = `history-asset:${++this.nextAsset}`; this.assetIds.set(value, id); this.assets.set(id, value); }
      return this.assetIds.get(value);
    });
  }
  decode(state) { return JSON.parse(state, (key, value) => key === 'dataUrl' && this.assets.has(value) ? this.assets.get(value) : value); }
  pruneAssets() {
    const used = new Set(this.states.flatMap(state => state.match(/history-asset:\d+/g) || []));
    for (const [id, data] of this.assets) if (!used.has(id)) { this.assets.delete(id); this.assetIds.delete(data); }
  }
  push(state, { mergeKey = '' } = {}) {
    if (this.busy) return false;
    const encoded = this.encode(state), now = Date.now();
    if (encoded === this.states[this.index]) return false;
    const merge = mergeKey && mergeKey === this.lastKey && now - this.lastTime < 700 && this.index > 0 && !this.canRedo();
    this.states.splice(this.index + 1);
    if (merge) this.states[this.index] = encoded;
    else { this.states.push(encoded); if (this.states.length > this.limit + 1) this.states.shift(); this.index = this.states.length - 1; }
    this.lastKey = mergeKey; this.lastTime = now;
    this.pruneAssets(); this.onChange(); return true;
  }
  async move(direction) {
    if (direction < 0 ? !this.canUndo() : !this.canRedo()) return false;
    const target = this.index + direction;
    this.busy = true; this.onChange();
    try { await this.restore(this.decode(this.states[target])); this.index = target; this.lastKey = ''; return true; }
    catch (error) { await this.restore(this.decode(this.states[this.index])); throw error; }
    finally { this.busy = false; this.onChange(); }
  }
  undo() { return this.move(-1); }
  redo() { return this.move(1); }
  clear(state) {
    if (this.busy) return;
    this.states = []; this.index = -1; this.assets.clear(); this.assetIds.clear(); this.lastKey = '';
    if (state) this.push(state); else this.onChange();
  }
}
