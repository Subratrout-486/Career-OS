const REPO_NEW_ISSUE = 'https://github.com/Subratrout-486/Career-OS/issues/new';
const FILL = 'career-os-fill-payload';
const READY = 'career-os-issue-ready';
const RESULT = 'career-os-fill-result';

function buildIssueBody(job) {
  return `<!-- CAREER_OS_JOB_V1 -->\n\nCareer OS browser capture. The JSON below is machine-readable; do not edit the fenced JSON unless correcting the job details.\n\n\`\`\`json\n${JSON.stringify(job, null, 2)}\n\`\`\`\n`;
}

async function sendPending(tabId) {
  const key = `pendingJob:${tabId}`;
  const stored = await chrome.storage.local.get(key);
  const pending = stored[key];
  if (!pending?.job) return { ok: false, reason: 'No pending Career OS payload found.' };
  try {
    await chrome.tabs.sendMessage(tabId, {
      type: FILL,
      tabId,
      body: buildIssueBody(pending.job)
    });
    return { ok: true };
  } catch (error) {
    return { ok: false, reason: error.message || 'GitHub content script is not ready.' };
  }
}

chrome.runtime.onMessage.addListener((message, sender) => {
  if (message?.type === READY) {
    const tabId = sender.tab?.id || message.tabId;
    if (tabId) sendPending(tabId).catch((error) => console.warn('Career OS ready handling failed:', error));
    return;
  }

  if (message?.type === RESULT) {
    const tabId = message.tabId || sender.tab?.id;
    if (!tabId) return;
    const key = `pendingJob:${tabId}`;
    if (message.ok) {
      chrome.storage.local.remove(key).catch((error) => console.warn('Career OS storage cleanup failed:', error));
    }
    return;
  }

  if (message?.type === 'career-os-fill-issue' && message.tabId) {
    sendPending(message.tabId).catch((error) => console.warn('Career OS fill request failed:', error));
  }
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== 'complete' || !tab.url?.startsWith(REPO_NEW_ISSUE)) return;
  // The content script owns DOM interaction. This message is only a fallback
  // for a content script that loaded before the pending payload was stored.
  const pending = await chrome.storage.local.get(`pendingJob:${tabId}`);
  if (pending[`pendingJob:${tabId}`]) {
    await new Promise((resolve) => setTimeout(resolve, 150));
    await sendPending(tabId);
  }
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  await chrome.storage.local.remove(`pendingJob:${tabId}`);
});
