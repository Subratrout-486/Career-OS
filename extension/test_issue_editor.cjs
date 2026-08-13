const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

class FakeEvent { constructor(type, options = {}) { this.type = type; Object.assign(this, options); } }
class FakeTextArea {
  constructor() { this._value = ''; this.disabled = false; this.events = []; this.tagName = 'TEXTAREA'; }
  get value() { return this._value; }
  set value(next) { this._value = String(next); }
  getClientRects() { return [{}]; }
  dispatchEvent(event) { this.events.push(event); return true; }
  focus() {}
}
class FakeContentEditable {
  constructor() { this.textContent = ''; this.innerText = ''; this.disabled = false; this.events = []; this.tagName = 'DIV'; }
  getClientRects() { return [{}]; }
  dispatchEvent(event) { this.events.push(event); return true; }
  focus() {}
}

function loadHelper(editor) {
  const source = fs.readFileSync(__dirname + '/issue-editor.js', 'utf8');
  const context = {
    module: { exports: {} }, exports: {},
    document: {
      querySelector: () => editor,
      createRange: () => ({ selectNodeContents() {} }),
      execCommand: () => false
    },
    window: { getSelection: () => ({ removeAllRanges() {}, addRange() {} }) },
    HTMLTextAreaElement: FakeTextArea,
    HTMLInputElement: class FakeInput {},
    InputEvent: FakeEvent,
    Event: FakeEvent,
    FocusEvent: FakeEvent,
    globalThis: {}
  };
  vm.runInNewContext(source, context, { filename: 'issue-editor.js' });
  return context.module.exports;
}

const job = {
  title: 'Support Engineer', company: 'Example Co', location: 'US-Remote',
  url: 'https://example.test/jobs/42', source: 'browser-extension',
  description: 'Full JD including \"quoted\" details.', captured_at: '2026-08-13T00:00:00.000Z'
};
const textarea = new FakeTextArea();
const { buildIssueBody, fillIssueEditor } = loadHelper(textarea);
const body = buildIssueBody(job);
assert(body.startsWith('<!-- CAREER_OS_JOB_V1 -->'));
assert(body.includes('"title": "Support Engineer"'));
assert(body.includes('"location": "US-Remote"'));
assert(body.includes('"description": "Full JD including \\\"quoted\\\" details."'));
assert.strictEqual(fillIssueEditor(body).ok, true);
assert.strictEqual(textarea.value, body);
assert(textarea.events.some((event) => event.type === 'input'));
assert.strictEqual(fillIssueEditor(body).alreadyFilled, true);

const contenteditable = new FakeContentEditable();
const contentApi = loadHelper(contenteditable);
const contentResult = contentApi.fillIssueEditor(body);
assert.strictEqual(contentResult.ok, true);
assert.strictEqual(contenteditable.textContent, body);
assert(contenteditable.events.some((event) => event.type === 'input'));

console.log('extension issue-editor regression passed');
