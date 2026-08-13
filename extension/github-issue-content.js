(() => {
  const READY = 'career-os-issue-ready';
  const FILL = 'career-os-fill-payload';
  const RESULT = 'career-os-fill-result';
  const MARKER = '<!-- CAREER_OS_JOB_V1 -->';
  const MAX_WAIT_MS = 20000;

  function textOf(el) {
    if (!el) return '';
    return ('value' in el ? el.value : (el.innerText || el.textContent || '') || '').trim();
  }

  function candidates(root = document) {
    const selectors = [
      'textarea[name="issue[body]"]', '#issue_body',
      'textarea[aria-label*="body" i]', 'textarea[placeholder*="body" i]',
      'textarea', '[contenteditable="true"][role="textbox"]',
      '[contenteditable="true"]', '[data-testid*="comment-editor"] [contenteditable="true"]',
      '.js-comment-field[contenteditable="true"]'
    ];
    const found = [];
    for (const selector of selectors) {
      try { found.push(...root.querySelectorAll(selector)); } catch (_) {}
    }
    if (root.querySelectorAll) {
      for (const el of root.querySelectorAll('*')) {
        if (el.shadowRoot) found.push(...candidates(el.shadowRoot));
      }
    }
    return found;
  }

  function findEditor() {
    return candidates().find((el) => !el.disabled && (el.getClientRects?.().length ?? 1) !== 0) || null;
  }

  function banner(ok, message) {
    const id = 'career-os-fill-status';
    let el = document.getElementById(id);
    if (!el) {
      el = document.createElement('div');
      el.id = id;
      document.body?.appendChild(el);
    }
    el.style.cssText = `position:fixed;z-index:2147483647;top:12px;right:12px;max-width:460px;padding:14px 16px;background:${ok ? '#166534' : '#b91c1c'};color:#fff;border:2px solid ${ok ? '#14532d' : '#7f1d1d'};border-radius:8px;font:600 14px/1.4 system-ui,sans-serif;box-shadow:0 4px 16px #0006;`;
    el.textContent = message;
  }

  function fire(el, type, data = null) {
    try {
      if (type === 'input') el.dispatchEvent(new InputEvent('input', { bubbles: true, composed: true, inputType: 'insertText', data }));
      else if (type === 'beforeinput') el.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, composed: true, inputType: 'insertText', data }));
      else el.dispatchEvent(new Event(type, { bubbles: true, composed: true }));
    } catch (_) {
      try { el.dispatchEvent(new Event(type, { bubbles: true })); } catch (_) {}
    }
  }

  function setTextarea(editor, body) {
    const proto = HTMLTextAreaElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    if (!setter) return false;
    setter.call(editor, body);
    fire(editor, 'input', body);
    fire(editor, 'change');
    editor.blur();
    return textOf(editor) === body;
  }

  function setContenteditable(editor, body) {
    editor.focus();
    try {
      const range = document.createRange();
      range.selectNodeContents(editor);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    } catch (_) {}
    let inserted = false;
    try { inserted = Boolean(document.execCommand?.('insertText', false, body)); } catch (_) {}
    if (!inserted || textOf(editor) !== body) editor.textContent = body;
    fire(editor, 'beforeinput', body);
    fire(editor, 'input', body);
    fire(editor, 'change');
    editor.dispatchEvent(new FocusEvent('blur', { bubbles: true }));
    return textOf(editor) === body;
  }

  async function fill(body) {
    const deadline = Date.now() + MAX_WAIT_MS;
    let lastReason = 'GitHub issue editor was not found.';
    while (Date.now() < deadline) {
      const editor = findEditor();
      if (editor) {
        const current = textOf(editor);
        if (current === body) return { ok: true, alreadyFilled: true };
        if (current.includes(MARKER)) return { ok: false, reason: 'The GitHub issue editor already contains a Career OS payload.' };
        const ok = editor instanceof HTMLTextAreaElement
          ? setTextarea(editor, body)
          : setContenteditable(editor, body);
        if (ok && textOf(editor) === body && textOf(editor).includes(MARKER)) return { ok: true, alreadyFilled: false };
        lastReason = 'GitHub did not retain the payload after input events.';
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    return { ok: false, reason: `${lastReason} Timed out after ${MAX_WAIT_MS / 1000}s.` };
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message?.type !== FILL || !message.body) return;
    fill(message.body).then((result) => {
      banner(result.ok, result.ok
        ? 'Career OS payload filled successfully. Review the title and captured JSON, then click “Submit new issue” yourself.'
        : `Career OS capture failed: ${result.reason} Do not submit this blank issue.`);
      chrome.runtime.sendMessage({ type: RESULT, tabId: message.tabId, ...result });
      sendResponse(result);
    }).catch((error) => {
      const result = { ok: false, reason: error.message || 'Unexpected editor error.' };
      banner(false, `Career OS capture failed: ${result.reason} Do not submit this blank issue.`);
      chrome.runtime.sendMessage({ type: RESULT, tabId: message.tabId, ...result });
      sendResponse(result);
    });
    return true;
  });

  chrome.runtime.sendMessage({ type: READY, tabId: undefined });
})();
