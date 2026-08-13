const $ = (id) => document.getElementById(id);

function clean(value) {
  return (value || '').replace(/\s+/g, ' ').trim();
}

async function extractJob(tab) {
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => {
      const firstText = (selectors) => {
        for (const selector of selectors) {
          const el = document.querySelector(selector);
          const value = el?.innerText?.trim() || el?.textContent?.trim();
          if (value) return value;
        }
        return '';
      };

      const title = firstText([
        'h1',
        '[data-testid*="job-title"]',
        '[class*="job-title"]'
      ]) || document.title;
      const company = firstText([
        '[data-testid*="company"]',
        '[class*="company"]',
        '[class*="employer"]'
      ]);
      const location = firstText([
        '[data-testid*="location"]',
        '[class*="location"]'
      ]);
      const description = firstText([
        '[data-testid*="job-description"]',
        '[class*="job-description"]',
        '[id*="job-description"]',
        'article',
        'main'
      ]) || document.body?.innerText || '';

      return { title, company, location, description };
    }
  });
  return result;
}

async function init() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) return;
  try {
    const job = await extractJob(tab);
    $('title').value = clean(job.title);
    $('company').value = clean(job.company);
    $('location').value = clean(job.location);
    $('url').value = tab.url || '';
    $('description').value = job.description || '';
  } catch (error) {
    $('status').textContent = `Could not read this page: ${error.message}`;
  }
}

$('send').addEventListener('click', async () => {
  const title = clean($('title').value);
  const company = clean($('company').value);
  const location = clean($('location').value);
  const url = $('url').value;
  const description = $('description').value.trim();

  if (!title || !description) {
    $('status').textContent = 'Please provide at least the job title and full job description.';
    return;
  }

  $('send').disabled = true;
  $('status').textContent = 'Opening Career OS intake…';

  const job = { title, company, location, url, source: 'browser-extension', description };
  const issueTitle = `Career OS Job — ${title}${company ? ` — ${company}` : ''}`;

  const issueTab = await chrome.tabs.create({
    url: `https://github.com/Subratrout-486/Career-OS/issues/new?title=${encodeURIComponent(issueTitle)}`,
    active: true
  });

  await chrome.storage.local.set({
    [`pendingJob:${issueTab.id}`]: { job, createdAt: Date.now() }
  });
  chrome.runtime.sendMessage({ type: 'career-os-fill-issue', tabId: issueTab.id });

  $('status').textContent = 'GitHub issue opened. Career OS will fill the full JD automatically; click Submit new issue there.';
});

init();
