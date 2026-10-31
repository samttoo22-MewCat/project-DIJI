// Run with jsdom available on NODE_PATH; this exercises the actual app event listeners.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const root = path.resolve(__dirname, '..');
const dom = new JSDOM(fs.readFileSync(path.join(root, 'ui/index.html'), 'utf8'), {
  url: 'https://example.test/', runScripts: 'outside-only',
});
const w = dom.window;
w.matchMedia = () => ({ matches: false, addEventListener() {} });
w.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
w.HTMLDialogElement.prototype.close = function () { this.open = false; };
w.fetch = async () => ({ ok: true, json: async () => ({ auth_required: true, authenticated: false, user: null }) });
let submissions = 0;
w.document.querySelector('#chat-form').requestSubmit = () => { submissions++; };
w.eval(fs.readFileSync(path.join(root, 'ui/app.js'), 'utf8'));
const input = w.document.querySelector('#chat-input');
function key(options) {
  const event = new w.KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true, ...options });
  input.dispatchEvent(event);
  return event;
}
try {
  input.value = '測試中文';
  input.dispatchEvent(new w.CompositionEvent('compositionstart', { bubbles: true, data: '測試中文' }));
  assert.equal(key({ isComposing: true, keyCode: 13 }).defaultPrevented, false, '選字確認應交給輸入法');
  assert.equal(submissions, 0, '組字中的 Enter 不可送出');
  input.dispatchEvent(new w.CompositionEvent('compositionend', { bubbles: true, data: '測試中文' }));
  assert.equal(key({ isComposing: false, keyCode: 229 }).defaultPrevented, false, 'Safari 結束組字的 Enter 不可攔截');
  assert.equal(submissions, 0, 'Safari 選字確認不可送出');
  assert.equal(input.value, '測試中文', '選字後文字仍保留');
  assert.equal(key({ isComposing: false, keyCode: 13 }).defaultPrevented, true);
  assert.equal(submissions, 1, '選字完成後再按 Enter 送出一次');
  assert.equal(key({ shiftKey: true, keyCode: 13 }).defaultPrevented, false);
  assert.equal(submissions, 1, 'Shift+Enter 保持換行');
  key({ key: 'a', keyCode: 65 });
  assert.equal(submissions, 1, '其他按鍵不送出');
  console.log('PASS: IME confirmation, Safari 229, committed Enter, Shift+Enter and retained input');
} finally {
  dom.window.close();
}
