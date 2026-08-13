function buildIssueBody(job) {
  return `<!-- CAREER_OS_JOB_V1 -->\n\nCareer OS browser capture. The JSON below is machine-readable; do not edit the fenced JSON unless correcting the job details.\n\n\`\`\`json\n${JSON.stringify(job, null, 2)}\n\`\`\`\n`;
}

function issueEditorCandidates() {
  return [
    'textarea[name="issue[body]"]',
    '#issue_body',
    'textarea[aria-label*="body" i]',
    'textarea[placeholder*="body" i]',
    'textarea',
    '[contenteditable="true"][role="textbox"]',
    '[contenteditable="true"]',
    '[data-testid*="comment-editor"] [contenteditable="true"]',
    '.js-comment-field[contenteditable="true"]'
  ];
}

function findIssueEditor() {
  for (const selector of issueEditorCandidates()) {
    try {
      const element = document.querySelector(selector);
      if (element && !element.disabled && element.getClientRects?.().length !== 0) return element;
    } catch (_) {}
  }
  return null;
}

function readEditorValue(editor) {
  if (!editor) return '';
  if (editor instanceof HTMLTextAreaElement || editor instanceof HTMLInputElement) return editor.value || '';
  return editor.innerText || editor.textContent || '';
}

function dispatchEditorEvent(editor, type, detail = {}) {
  const event = type === 'input'
    ? new InputEvent(type, { bubbles: true, composed: true, inputType: 'insertText', data: detail.data || null })
    : new Event(type, { bubbles: true, composed: true });
  editor.dispatchEvent(event);
}

function setTextareaValue(editor, body) {
  const prototype = Object.getPrototypeOf(editor);
  const descriptor = Object.getOwnPropertyDescriptor(prototype, 'value') ||
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value');
  if (!descriptor?.set) return false;
  descriptor.set.call(editor, body);
  dispatchEditorEvent(editor, 'input', { data: body });
  dispatchEditorEvent(editor, 'change');
  return readEditorValue(editor) === body;
}

function setContenteditableValue(editor, body) {
  editor.focus();
  const selection = window.getSelection?.();
  const range = document.createRange?.();
  if (selection && range) {
    range.selectNodeContents(editor);
    selection.removeAllRanges();
    selection.addRange(range);
  }
  let inserted = false;
  try { inserted = Boolean(document.execCommand?.('insertText', false, body)); } catch (_) {}
  if (!inserted || readEditorValue(editor) !== body) {
    editor.textContent = body;
  }
  dispatchEditorEvent(editor, 'beforeinput');
  dispatchEditorEvent(editor, 'input', { data: body });
  dispatchEditorEvent(editor, 'change');
  editor.dispatchEvent(new FocusEvent('blur', { bubbles: true }));
  return readEditorValue(editor) === body;
}

function fillIssueEditor(body) {
  const editor = findIssueEditor();
  if (!editor) return { ok: false, reason: 'GitHub issue editor was not found yet.' };
  const current = readEditorValue(editor);
  if (current === body) return { ok: true, editor: editor.tagName.toLowerCase(), alreadyFilled: true };
  if (current.includes('<!-- CAREER_OS_JOB_V1 -->')) {
    return { ok: false, reason: 'The GitHub issue editor already contains a Career OS payload.' };
  }
  const ok = editor instanceof HTMLTextAreaElement || editor instanceof HTMLInputElement
    ? setTextareaValue(editor, body)
    : setContenteditableValue(editor, body);
  return ok
    ? { ok: true, editor: editor.tagName.toLowerCase(), alreadyFilled: false }
    : { ok: false, reason: 'GitHub did not accept or retain the Career OS issue body.' };
}

function showIssueFillFailure(message) {
  const id = 'career-os-fill-error';
  let banner = document.getElementById(id);
  if (!banner) {
    banner = document.createElement('div');
    banner.id = id;
    banner.style.cssText = 'position:fixed;z-index:2147483647;top:12px;right:12px;max-width:420px;padding:14px 16px;background:#b91c1c;color:#fff;border:2px solid #7f1d1d;border-radius:8px;font:600 14px/1.4 system-ui,sans-serif;box-shadow:0 4px 16px #0006;';
    document.body?.appendChild(banner);
  }
  banner.textContent = `Career OS capture failed: ${message} Do not submit this blank issue. Close it and retry the capture.`;
}

function showIssueFillSuccess() {
  const id = 'career-os-fill-success';
  let banner = document.getElementById(id);
  if (!banner) {
    banner = document.createElement('div');
    banner.id = id;
    banner.style.cssText = 'position:fixed;z-index:2147483647;top:12px;right:12px;max-width:420px;padding:12px 14px;background:#166534;color:#fff;border:2px solid #14532d;border-radius:8px;font:600 14px/1.4 system-ui,sans-serif;box-shadow:0 4px 16px #0006;';
    document.body?.appendChild(banner);
  }
  banner.textContent = 'Career OS payload filled. Review the title and full JSON, then submit the GitHub issue yourself.';
}

if (typeof globalThis !== 'undefined') {
  Object.assign(globalThis, { buildIssueBody, fillIssueEditor, showIssueFillFailure, showIssueFillSuccess });
}

if (typeof module !== 'undefined') module.exports = { buildIssueBody, issueEditorCandidates, readEditorValue, fillIssueEditor };

