// Minimal DOM so the report's script can be EXECUTED, not merely parsed. A
// syntax check cannot catch $("#c-err") returning null and .remove() throwing,
// which is a blank viewer rather than an error anyone sees.
const made = new Map();
function el(id) {
  if (made.has(id)) return made.get(id);
  const node = {
    id, hidden: false, innerHTML: "", dataset: {}, style: {}, attrs: {},
    clientWidth: 900, clientHeight: 560, width: 900, height: 560,
    parentElement: null, _children: [],
    setAttribute(k, v) { this.attrs[k] = v; },
    getAttribute(k) { return this.attrs[k]; },
    removeAttribute(k) { delete this.attrs[k]; },
    remove() { made.delete(id); removed.push(id); },
    addEventListener() {}, removeEventListener() {},
    setPointerCapture() {}, releasePointerCapture() {},
    querySelectorAll(sel) {
      // the cloud selector writes buttons into innerHTML then queries them back
      const n = (this.innerHTML.match(/<button/g) || []).length;
      return Array.from({length: n}, (_, i) => {
        const b = el(`${id}-btn-${i}`);
        b.dataset.cloud = String(i);
        return b;
      });
    },
    getContext() { return ctx2d; },
    getBoundingClientRect() { return {left: 0, top: 0, width: 900, height: 560}; },
  };
  node.parentElement = {style: {}, id: id + "-parent"};
  made.set(id, node);
  return node;
}
const removed = [];
const ctx2d = new Proxy({}, {get: () => () => {}});
global.removed = removed;
global.document = {
  documentElement: el("root"),
  querySelector: (sel) => {
    const id = sel.replace(/^#/, "");
    return made.has(id) || KNOWN.has(id) ? el(id) : null;
  },
  querySelectorAll: () => [],
  addEventListener() {},
  createElement: () => el("tmp"),
};
const KNOWN = new Set([
  "subtitle","hero","viewer","c-rgb","c-err","c-cam","c-pts","c-clouds","c-reset",
  "legend","tried","tried-sub","steps","table","downloads","downloads-card",
  "downloads-note",
]);
global.window = {
  devicePixelRatio: 1, addEventListener() {}, matchMedia: () => ({addEventListener(){}}),
};
global.matchMedia = global.window.matchMedia;
global.getComputedStyle = () => ({getPropertyValue: () => "#111114"});
global.atob = (b64) => Buffer.from(b64, "base64").toString("binary");
global.requestAnimationFrame = (f) => f();
