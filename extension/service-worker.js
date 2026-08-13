const REPO_NEW_ISSUE = 'https://github.com/Subratrout-486/Career-OS/issues/new';

function buildIssueBody(job) {
  return `<!-- CAREER_OS_JOB_V1 -->\n\nCareer OS browser capture. The JSON below is machine-readable; do not edit the fenced JSON unless correcting the job details.\n\n\`\`\`json\n${JSON.stringify(job, null, 2)}\n\`\`\`\n`;
}

async function fillIssueTab(tabId, job) {
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    args: [buildIssueBody(job)],
    func: (body) => {
      const textarea = document.querySelector('textarea[name="issue[body]"]') ||
        document.querySelector('#issue_body') ||
        document.querySelector('textarea');
      if (!textarea) return false;
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
      setter.call(textarea, body);
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
      textarea.dispatchEvent(new Event('change', { bubbles: true }));
      textarea.focus();
      return true;
    }
  });
  return Boolean(results?.[0]?.result);
}

async function tryFillPending(tabId) {
  const key = `pendingJob:${tabId}`;
  const stored = await chrome.storage.local.get(key);
  const pending = stored[key];
  if (!pending) return false;

  try {
    const ok = await fillIssueTab(tabId, pending.job);
    if (ok) {
      await chrome.storage.local.remove(key);
      return true;
    }
  } catch (error) {
    console.warn('Career OS could not fill GitHub issue:', error);
  }
  return false;
}

chrome.runtime.onMessage.addListener((message, sender) => {
  if (message?.type !== 'career-os-fill-issue' || !message.tabId) return;
  tryFillPending(message.tabId);
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== 'complete' || !tab.url?.startsWith(REPO_NEW_ISSUE)) return;
  await tryFillPending(tabId);
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  await chrome.storage.local.remove(`pendingJob:${tabId}`);
});
