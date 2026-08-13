importScripts('issue-editor.js');

const REPO_NEW_ISSUE = 'https://github.com/Subratrout-486/Career-OS/issues/new';
const MAX_FILL_ATTEMPTS = 15;
const RETRY_DELAY_MS = 750;

async function fillIssueTab(tabId, job) {
  const body = buildIssueBody(job);
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    args: [body],
    func: (payload) => {
      const selectors = [
        'textarea[name="issue[body]"]', '#issue_body',
        'textarea[aria-label*="body" i]', 'textarea[placeholder*="body" i]',
        'textarea', '[contenteditable="true"][role="textbox"]',
        '[contenteditable="true"]', '[data-testid*="comment-editor"] [contenteditable="true"]'
      ];
      const editor = selectors.map((selector) => {
        try { return document.querySelector(selector); } catch (_) { return null; }
      }).find((element) => element && !element.disabled && (element.getClientRects?.().length ?? 1) !== 0);
      if (!editor) return { ok: false, reason: 'GitHub issue editor was not found yet.' };
      const read = () => ('value' in editor ? editor.value : (editor.innerText || editor.textContent || '')) || '';
      if (read() === payload) return { ok: true, alreadyFilled: true };
      if (read().includes('<!-- CAREER_OS_JOB_V1 -->')) {
        return { ok: false, reason: 'The GitHub issue editor already contains a Career OS payload.' };
      }
      const dispatch = (type, inputType = 'insertText') => {
        const event = type === 'input'
          ? new InputEvent(type, { bubbles: true, composed: true, inputType, data: payload })
          : new Event(type, { bubbles: true, composed: true });
        editor.dispatchEvent(event);
      };
      let success = false;
      if (editor instanceof HTMLTextAreaElement || editor instanceof HTMLInputElement) {
        const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(editor), 'value') ||
          Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value');
        if (descriptor?.set) descriptor.set.call(editor, payload);
        dispatch('input');
        dispatch('change');
        success = read() === payload;
      } else {
        editor.focus();
        try {
          const range = document.createRange();
          range.selectNodeContents(editor);
          const selection = window.getSelection();
          selection?.removeAllRanges();
          selection?.addRange(range);
        } catch (_) {}
        let inserted = false;
        try { inserted = Boolean(document.execCommand?.('insertText', false, payload)); } catch (_) {}
        if (!inserted || read() !== payload) editor.textContent = payload;
        dispatch('beforeinput');
        dispatch('input');
        dispatch('change');
        editor.dispatchEvent(new FocusEvent('blur', { bubbles: true }));
        success = read() === payload;
      }
      return success ? { ok: true, alreadyFilled: false } : { ok: false, reason: 'GitHub did not accept or retain the Career OS issue body.' };
    }
  });
  return results?.[0]?.result || { ok: false, reason: 'GitHub injection returned no result.' };
}

async function showTabMessage(tabId, type, message) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      args: [message],
      func: (text) => {
        const id = 'career-os-fill-status';
        let banner = document.getElementById(id);
        if (!banner) {
          banner = document.createElement('div');
          banner.id = id;
          banner.style.cssText = 'position:fixed;z-index:2147483647;top:12px;right:12px;max-width:440px;padding:14px 16px;color:#fff;border-radius:8px;font:600 14px/1.4 system-ui,sans-serif;box-shadow:0 4px 16px #0006;';
          document.body?.appendChild(banner);
        }
        banner.style.background = text.startsWith('ERROR:') ? '#b91c1c' : '#166534';
        banner.textContent = text.replace(/^ERROR:\s*/, '');
      }
    });
  } catch (error) {
    console.warn(`Career OS could not show ${type} status:`, error);
  }
}

async function tryFillPending(tabId) {
  const key = `pendingJob:${tabId}`;
  const stored = await chrome.storage.local.get(key);
  const pending = stored[key];
  if (!pending) return { ok: false, reason: 'No pending Career OS payload found.' };
  try {
    const result = await fillIssueTab(tabId, pending.job);
    if (result.ok) {
      await chrome.storage.local.remove(key);
      await showTabMessage(tabId, 'success', 'Career OS payload filled. Review the title and full JSON, then submit the GitHub issue yourself.');
      return result;
    }
    return result;
  } catch (error) {
    console.warn('Career OS could not fill GitHub issue:', error);
    return { ok: false, reason: error.message || 'Unexpected GitHub editor error.' };
  }
}

async function retryFillPending(tabId) {
  let lastReason = 'GitHub issue editor was not ready.';
  for (let attempt = 1; attempt <= MAX_FILL_ATTEMPTS; attempt += 1) {
    const key = `pendingJob:${tabId}`;
    const stored = await chrome.storage.local.get(key);
    if (!stored[key]) return true;
    const result = await tryFillPending(tabId);
    if (result.ok) return true;
    lastReason = result.reason || lastReason;
    if (attempt < MAX_FILL_ATTEMPTS) await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY_MS));
  }
  const error = `ERROR: ${lastReason} Retried ${MAX_FILL_ATTEMPTS} times. Do not submit this blank issue; close it and retry capture.`;
  await showTabMessage(tabId, 'error', error);
  console.warn(`Career OS could not fill GitHub issue tab ${tabId}: ${lastReason}`);
  return false;
}

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type !== 'career-os-fill-issue' || !message.tabId) return;
  retryFillPending(message.tabId);
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== 'complete' || !tab.url?.startsWith(REPO_NEW_ISSUE)) return;
  retryFillPending(tabId);
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  await chrome.storage.local.remove(`pendingJob:${tabId}`);
});
