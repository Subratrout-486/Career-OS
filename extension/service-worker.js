const REPO_NEW_ISSUE = 'https://github.com/Subratrout-486/Career-OS/issues/new';

function buildIssueBody(job) {
  return `<!-- CAREER_OS_JOB_V1 -->\n\nCareer OS browser capture. The JSON below is machine-readable; do not edit the fenced JSON unless correcting the job details.\n\n\`\`\`json\n${JSON.stringify(job, null, 2)}\n\`\`\`\n`;
}

async function fillIssueTab(tabId, job) {
  await chrome.scripting.executeScript({
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
}

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== 'complete' || !tab.url?.startsWith(REPO_NEW_ISSUE)) return;
  const key = `pendingJob:${tabId}`;
  const stored = await chrome.storage.local.get(key);
  const pending = stored[key];
  if (!pending) return;

  try {
    const ok = await fillIssueTab(tabId, pending.job);
    if (ok) await chrome.storage.local.remove(key);
  } catch (error) {
    console.warn('Career OS could not fill GitHub issue:', error);
  }
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  await chrome.storage.local.remove(`pendingJob:${tabId}`);
});
