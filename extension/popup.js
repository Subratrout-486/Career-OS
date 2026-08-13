const $ = (id) => document.getElementById(id);

function clean(value) {
  return (value || '').replace(/\s+/g, ' ').trim();
}

async function extractJob(tab) {
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => {
      const text = document.body?.innerText || '';
      const meta = (name) => document.querySelector(`meta[name="${name}"]`)?.content || '';
      const og = (property) => document.querySelector(`meta[property="${property}"]`)?.content || '';
      const first = (selectors) => {
        for (const selector of selectors) {
          const el = document.querySelector(selector);
          if (el?.innerText?.trim()) return el.innerText.trim();
          if (el?.textContent?.trim()) return el.textContent.trim();
        }
        return '';
      };

      const title = first(['h1', '[data-testid*="job-title"]', '[class*="job-title"]']) || document.title;
      const company = first(['[data-testid*="company"]', '[class*="company"]', '[class*="employer"]']);
      const location = first(['[data-testid*="location"]', '[class*="location"]']);

      return {
        title,
        company,
        location,
        url: location.href,
        description: text,
        source: 'browser-extension'
      };
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
    $('url').value = tab.url || job.url || '';
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

  const tab = await chrome.tabs.create({
    url: `https://github.com/Subratrout-486/Career-OS/issues/new?title=${encodeURIComponent(issueTitle)}`,
    active: true
  });

  await chrome.storage.local.set({
    [`pendingJob:${tab.id}`]: { job, createdAt: Date.now() }
  });

  $('status').textContent = 'GitHub issue opened. Career OS will fill the full JD automatically; click Submit new issue there.';
});

init();
