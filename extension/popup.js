const $ = (id) => document.getElementById(id);

function clean(value) {
  return (value || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
}

function normalizeJobUrl(url) {
  try {
    const parsed = new URL(url || '');
    if (parsed.hostname.includes('linkedin.com')) {
      const match = parsed.pathname.match(/\/jobs\/view\/(\d+)/);
      if (match) return `https://www.linkedin.com/jobs/view/${match[1]}/`;
    }
    return url || '';
  } catch {
    return url || '';
  }
}

async function extractJob(tab) {
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: async () => {
      const isLinkedIn = location.hostname.includes('linkedin.com');

      const text = (el) => (el?.innerText || el?.textContent || '').trim();
      const firstText = (selectors) => {
        for (const selector of selectors) {
          const el = document.querySelector(selector);
          const value = text(el);
          if (value) return value;
        }
        return '';
      };

      const firstElement = (selectors) => {
        for (const selector of selectors) {
          const el = document.querySelector(selector);
          if (el) return el;
        }
        return null;
      };

      // LinkedIn is a dynamic SPA and its generic class names can match
      // navigation/search UI. Prefer the job-detail container selectors first.
      if (isLinkedIn) {
        // Expand the description when LinkedIn exposes a "Show more" control.
        const showMore = [...document.querySelectorAll('button, a')].find((el) => {
          const label = text(el).toLowerCase();
          return label === 'show more' || label === 'see more';
        });
        if (showMore) showMore.click();
        await new Promise((resolve) => setTimeout(resolve, 300));

        const title = firstText([
          'h1.jobs-unified-top-card__job-title',
          'h1.top-card-layout__title',
          'h1.job-details-jobs-unified-top-card__job-title',
          '[data-testid="job-title"]',
          'h1'
        ]);

        const company = firstText([
          '.jobs-unified-top-card__company-name a',
          '.jobs-unified-top-card__company-name',
          '.job-details-jobs-unified-top-card__company-name a',
          '.job-details-jobs-unified-top-card__company-name',
          '.topcard__org-name-link',
          'a[href*="/company/"]'
        ]);

        let location = firstText([
          '.jobs-unified-top-card__bullet',
          '.jobs-unified-top-card__primary-description-container .jobs-unified-top-card__bullet',
          '.job-details-jobs-unified-top-card__primary-description-container .jobs-unified-top-card__bullet',
          '.job-details-jobs-unified-top-card__primary-description-container'
        ]);

        // The primary-description container can contain several metadata values.
        // Keep only the first useful location-like segment when possible.
        if (location.includes('·')) location = location.split('·')[0].trim();

        const descriptionEl = firstElement([
          '.jobs-description__content .jobs-box__html-content',
          '.jobs-description-content__text',
          '.jobs-description__content',
          '.description__text',
          '#jobDescriptionText',
          '[data-testid="job-details"]'
        ]);

        const description = text(descriptionEl);

        // If the page uses a newer structure, find the visible section headed
        // "About the job" and use its following content rather than the whole page.
        let fallbackDescription = '';
        if (!description) {
          const headings = [...document.querySelectorAll('h2, h3, h4')];
          const about = headings.find((el) => /about the job/i.test(text(el)));
          if (about) {
            const section = about.closest('section') || about.parentElement;
            fallbackDescription = text(section);
          }
        }

        const canonicalLink = firstElement([
          'link[rel="canonical"]',
          'a[href*="/jobs/view/"]'
        ]);

        return {
          title: title || document.title,
          company,
          location,
          description: description || fallbackDescription,
          canonicalUrl: canonicalLink?.href || location?.href || ''
        };
      }

      const title = firstText([
        '[data-testid*="job-title"]',
        '[class*="job-title"]',
        'h1'
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
        'article'
      ]) || document.body?.innerText || '';

      return { title, company, location, description, canonicalUrl: '' };
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
    $('url').value = normalizeJobUrl(job.canonicalUrl || tab.url || '');
    $('description').value = job.description || '';

    if (!job.company || !job.location || !job.description) {
      $('status').textContent = 'LinkedIn page detected, but one or more fields could not be extracted. Do not send yet.';
    }
  } catch (error) {
    $('status').textContent = `Could not read this page: ${error.message}`;
  }
}

$('send').addEventListener('click', async () => {
  const title = clean($('title').value);
  const company = clean($('company').value);
  const location = clean($('location').value);
  const url = normalizeJobUrl($('url').value);
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
