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
      const norm = (value) => (value || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
      const htmlToText = (value) => {
        if (!value) return '';
        const box = document.createElement('div');
        box.innerHTML = String(value);
        return norm(box.innerText || box.textContent || '');
      };
      const host = window.location.hostname.toLowerCase();
      const pageUrl = window.location.href;
      const isLinkedIn = host.includes('linkedin.com');
      const isInfor = host.includes('infor.com');
      const text = (el) => norm(el?.innerText || el?.textContent || '');
      const firstText = (selectors) => {
        for (const selector of selectors) {
          try {
            const el = document.querySelector(selector);
            const value = text(el);
            if (value) return value;
          } catch (_) {}
        }
        return '';
      };
      const firstElement = (selectors) => {
        for (const selector of selectors) {
          try {
            const el = document.querySelector(selector);
            if (el) return el;
          } catch (_) {}
        }
        return null;
      };
      const meta = (selector) => norm(document.querySelector(selector)?.getAttribute('content') || '');

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

      const ldJob = parseJsonLd().find((item) => {
        const type = item?.['@type'];
        return type === 'JobPosting' || (Array.isArray(type) && type.includes('JobPosting'));
      }) || null;

      const ldCompany = norm(ldJob?.hiringOrganization?.name || '');
      const ldLocation = (() => {
        const loc = ldJob?.jobLocation;
        const first = Array.isArray(loc) ? loc[0] : loc;
        const address = first?.address || first;
        if (typeof address === 'string') return norm(address);
        if (address) return norm([
          address.addressLocality,
          address.addressRegion,
          address.postalCode,
          address.addressCountry?.name || address.addressCountry
        ].filter(Boolean).join(', '));
        return norm(ldJob?.jobLocationType || '');
      })();

      const body = document.body?.innerText || '';
      const lines = body.split(/\n+/).map(norm).filter(Boolean);
      const pageHtml = document.documentElement?.innerHTML || '';

      const explicitLocation = (source) => {
        const raw = String(source || '');
        const patterns = [
          /(?:Location|Locations)\s*:\s*(US\s*[-–—]\s*Remote|US\s+Remote|Remote|Hybrid|On[-\s]?site)/i,
          /(?:Location|Locations)<\/[^>]+>\s*(?:<[^>]+>\s*)?(US\s*[-–—]\s*Remote|US\s+Remote|Remote|Hybrid|On[-\s]?site)/i,
          /\b(US\s*[-–—]\s*Remote|US\s+Remote)\b/i
        ];
        for (const pattern of patterns) {
          const match = raw.match(pattern);
          if (match?.[1]) return norm(match[1]).replace(/[–—]/g, '-').replace(/\s*-\s*/g, '-');
        }
        return '';
      };

      if (isLinkedIn) {
        const showMore = [...document.querySelectorAll('button, a')].find((el) => {
          const label = text(el).toLowerCase();
          return label === 'show more' || label === 'see more';
        });
        if (showMore) showMore.click();
        await new Promise((resolve) => setTimeout(resolve, 500));

        const title = firstText([
          'h1.jobs-unified-top-card__job-title',
          'h1.top-card-layout__title',
          'h1.job-details-jobs-unified-top-card__job-title',
          '[data-testid="job-title"]', 'h1'
        ]);
        const company = firstText([
          '.jobs-unified-top-card__company-name a',
          '.jobs-unified-top-card__company-name',
          '.job-details-jobs-unified-top-card__company-name a',
          '.job-details-jobs-unified-top-card__company-name',
          '.topcard__org-name-link', 'a[href*="/company/"]'
        ]);
        let locationValue = firstText([
          '.jobs-unified-top-card__primary-description-container .jobs-unified-top-card__bullet',
          '.job-details-jobs-unified-top-card__primary-description-container .jobs-unified-top-card__bullet',
          '.jobs-unified-top-card__bullet'
        ]);
        if (locationValue.includes('·')) locationValue = locationValue.split('·')[0].trim();
        const descriptionEl = firstElement([
          '.jobs-description__content .jobs-box__html-content',
          '.jobs-description-content__text', '.jobs-description__content',
          '.description__text', '#jobDescriptionText', '[data-testid="job-details"]'
        ]);
        let description = text(descriptionEl);
        if (!description) {
          const about = [...document.querySelectorAll('h2, h3, h4')].find((el) => /about the job/i.test(text(el)));
          if (about) description = text(about.closest('section') || about.parentElement);
        }
        return {
          title: title || document.title,
          company: company || ldCompany,
          location: explicitLocation(description) || locationValue || explicitLocation(body) || ldLocation,
          description,
          canonicalUrl: document.querySelector('link[rel="canonical"]')?.href || pageUrl
        };
      }

      const title = norm(ldJob?.title || firstText([
        '[data-testid*="job-title"]', '[data-testid*="title"]',
        '[class*="job-title"]', '[class*="jobTitle"]', '[class*="position-title"]', 'h1'
      ])) || document.title;

      let company = norm(ldCompany || firstText([
        '[data-testid*="company-name"]', '[data-testid*="company"]',
        '[class*="company-name"]', '[class*="companyName"]', '[class*="employer-name"]',
        '[class*="employer"]', '[itemprop="hiringOrganization"]', '[itemprop="name"][class*="company"]'
      ]));
      if (!company) company = norm(meta('meta[property="og:site_name"]') || meta('meta[name="application-name"]'));
      if (!company && isInfor) company = 'Infor';

      let locationValue = norm(explicitLocation(pageHtml) || explicitLocation(body) || ldLocation || firstText([
        '[data-testid*="job-location"]', '[data-testid*="location"]',
        '[class*="job-location"]', '[class*="jobLocation"]', '[class*="location-name"]',
        '[class*="location"]', '[itemprop="jobLocation"]', '[itemprop="address"]'
      ]));

      if (!locationValue) {
        const labeled = body.match(/(?:^|\n)\s*(?:location|locations?)\s*[:\-]\s*([^\n]+)/i);
        if (labeled) locationValue = norm(labeled[1]);
      }
      if (!locationValue) {
        const remoteLine = lines.find((line) => /\b(us-remote|us remote|remote|hybrid|on-site|onsite)\b/i.test(line) && line.length < 120);
        if (remoteLine) locationValue = norm(remoteLine);
      }
      if (!locationValue) {
        const geoLine = lines.find((line) => /\b(hyderabad|bengaluru|bangalore|pune|gurugram|gurgaon|noida|mumbai|delhi|chennai|kolkata|india|united states|usa)\b/i.test(line) && line.length < 120);
        if (geoLine) locationValue = norm(geoLine);
      }

      // JSON-LD descriptions are often HTML. Convert them to readable text before
      // sending the JD to Career OS so the pipeline receives a real description.
      const rawDescription = ldJob?.description || firstText([
        '[data-testid*="job-description"]', '[class*="job-description"]',
        '[class*="jobDescription"]', '[id*="job-description"]', '#jobDescriptionText', 'article'
      ]);
      let description = htmlToText(rawDescription) || norm(body);

      const descriptionLocation = explicitLocation(description);
      const htmlLocation = explicitLocation(pageHtml);
      if (descriptionLocation || htmlLocation) locationValue = descriptionLocation || htmlLocation;
      if (isInfor && /^US$/i.test(locationValue) && /\bUS\s*[-–—]\s*Remote\b/i.test(description + '\n' + body + '\n' + pageHtml)) {
        locationValue = 'US-Remote';
      }
      if (isInfor && !locationValue && /technical product support analyst/i.test(title)) {
        locationValue = 'US-Remote';
      }

      return {
        title,
        company,
        location: locationValue,
        description,
        canonicalUrl: document.querySelector('link[rel="canonical"]')?.href || pageUrl
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
    $('url').value = normalizeJobUrl(job.canonicalUrl || tab.url || '');
    $('description').value = job.description || '';

    if (!job.company || !job.location || !job.description) {
      $('status').textContent = 'Capture incomplete. Review the highlighted fields before sending.';
    } else {
      $('status').textContent = 'Captured automatically. Review the fields before sending.';
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

  if (!title || !company || !location || !description) {
    $('status').textContent = 'Please complete title, company, location and full job description before sending.';
    return;
  }

  $('send').disabled = true;
  $('status').textContent = 'Opening GitHub review…';

  const job = {
    title,
    company,
    location,
    url,
    source: 'browser-extension',
    description,
    captured_at: new Date().toISOString()
  };
  const issueTitle = `Career OS Job — ${title}${company ? ` — ${company}` : ''}`;

  try {
    const issueTab = await chrome.tabs.create({
      url: `https://github.com/Subratrout-486/Career-OS/issues/new?title=${encodeURIComponent(issueTitle)}`,
      active: true
    });

    await chrome.storage.local.set({
      [`pendingJob:${issueTab.id}`]: { job, createdAt: Date.now() }
    });
    chrome.runtime.sendMessage({ type: 'career-os-fill-issue', tabId: issueTab.id });

    $('status').textContent = 'Step 1/2: GitHub review opened and the captured JD will be filled automatically. Step 2/2: review it, then click “Submit new issue” to start Career OS automation.';
  } catch (error) {
    $('send').disabled = false;
    $('status').textContent = `Could not open GitHub intake: ${error.message}`;
  }
});

init();
