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
      const host = location.hostname.toLowerCase();
      const isLinkedIn = host.includes('linkedin.com');
      const isInfor = host.includes('infor.com');

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
      const meta = (selector) => clean(document.querySelector(selector)?.getAttribute('content') || '');

      function parseJsonLd() {
        const records = [];
        for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
          try {
            const parsed = JSON.parse(script.textContent || '');
            if (Array.isArray(parsed)) records.push(...parsed);
            else if (parsed?.['@graph']) records.push(...parsed['@graph']);
            else records.push(parsed);
          } catch (_) {}
        }
        return records;
      }

      function jsonLdJob() {
        return parseJsonLd().find((item) => {
          const type = item?.['@type'];
          return type === 'JobPosting' || (Array.isArray(type) && type.includes('JobPosting'));
        }) || null;
      }

      function jsonLdLocation(job) {
        const loc = job?.jobLocation;
        const first = Array.isArray(loc) ? loc[0] : loc;
        const address = first?.address || first;
        if (typeof address === 'string') return clean(address);
        if (address) {
          return clean([
            address.addressLocality,
            address.addressRegion,
            address.postalCode,
            address.addressCountry?.name || address.addressCountry
          ].filter(Boolean).join(', '));
        }
        return clean(job?.jobLocationType || '');
      }

      const ldJob = jsonLdJob();
      const ldCompany = clean(ldJob?.hiringOrganization?.name || '');
      const ldLocation = jsonLdLocation(ldJob);

      if (isLinkedIn) {
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
          '.jobs-unified-top-card__primary-description-container .jobs-unified-top-card__bullet',
          '.job-details-jobs-unified-top-card__primary-description-container .jobs-unified-top-card__bullet',
          '.jobs-unified-top-card__bullet'
        ]);
        if (location.includes('·')) location = location.split('·')[0].trim();
        const descriptionEl = firstElement([
          '.jobs-description__content .jobs-box__html-content',
          '.jobs-description-content__text',
          '.jobs-description__content',
          '.description__text',
          '#jobDescriptionText',
          '[data-testid="job-details"]'
        ]);
        let description = text(descriptionEl);
        if (!description) {
          const about = [...document.querySelectorAll('h2, h3, h4')].find((el) => /about the job/i.test(text(el)));
          if (about) description = text(about.closest('section') || about.parentElement);
        }
        const canonical = document.querySelector('link[rel="canonical"]')?.href || location.href || '';
        return { title: title || document.title, company, location, description, canonicalUrl: canonical };
      }

      // Generic extraction: structured JobPosting data first, then semantic/meta selectors.
      const title = clean(ldJob?.title || firstText([
        '[data-testid*="job-title"]', '[data-testid*="title"]',
        '[class*="job-title"]', '[class*="jobTitle"]', '[class*="position-title"]', 'h1'
      ])) || document.title;

      let company = clean(ldCompany || firstText([
        '[data-testid*="company-name"]', '[data-testid*="company"]',
        '[class*="company-name"]', '[class*="companyName"]', '[class*="employer-name"]',
        '[class*="employer"]', '[itemprop="hiringOrganization"]', '[itemprop="name"][class*="company"]'
      ]));

      if (!company) company = clean(meta('meta[property="og:site_name"]') || meta('meta[name="application-name"]'));
      if (!company && isInfor) company = 'Infor';

      let location = clean(ldLocation || firstText([
        '[data-testid*="job-location"]', '[data-testid*="location"]',
        '[class*="job-location"]', '[class*="jobLocation"]', '[class*="location-name"]',
        '[class*="location"]', '[itemprop="jobLocation"]', '[itemprop="address"]'
      ]));

      const body = document.body?.innerText || '';
      const lines = body.split(/\n+/).map(clean).filter(Boolean);

      // Infor and similar ATS pages often expose the location only as visible text,
      // not as a stable class. Prefer an explicit Location label or common remote form.
      if (!location) {
        const labeled = body.match(/(?:^|\n)\s*(?:location|locations?)\s*[:\-]\s*([^\n]+)/i);
        if (labeled) location = clean(labeled[1]);
      }
      if (!location) {
        const remoteLine = lines.find((line) => /\b(remote|hybrid|on-site|onsite)\b/i.test(line) && line.length < 120);
        if (remoteLine) location = clean(remoteLine);
      }
      if (!location) {
        const geoLine = lines.find((line) => /\b(hyderabad|bengaluru|bangalore|pune|gurugram|gurgaon|noida|mumbai|delhi|chennai|kolkata|india|united states|usa)\b/i.test(line) && line.length < 100);
        if (geoLine) location = clean(geoLine);
      }

      let description = clean(ldJob?.description || firstText([
        '[data-testid*="job-description"]', '[class*="job-description"]',
        '[class*="jobDescription"]', '[id*="job-description"]', '#jobDescriptionText', 'article'
      ]));
      if (!description) description = body;

      const canonicalUrl = document.querySelector('link[rel="canonical"]')?.href || location.href || '';
      return { title, company, location, description, canonicalUrl };
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
      $('status').textContent = 'One or more fields could not be extracted. Review them before sending.';
    } else {
      $('status').textContent = 'Job captured. Review the fields before sending.';
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
