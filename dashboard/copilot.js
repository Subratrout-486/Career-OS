/* CareerPilot Job Copilot — presentation-layer MVP.
 * Uses the canonical profile already stored in Career OS. It never invents evidence,
 * never writes Notion/application state, and opens the employer/ATS URL for the user
 * to complete the application manually.
 */
(() => {
  const E = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const $ = s => document.querySelector(s);

  const PROFILE = {
    name: 'Subrat Rout',
    location: 'Hyderabad, India',
    education: 'Bachelor of Commerce (Accounting Hons) — North Orissa University',
    summary: 'Production support engineer with nearly 3 years leading incident response and root cause analysis for mission-critical, 24/7 enterprise systems, handling 8–10 production incidents daily at ~98.6% SLA compliance. Builds Python automation and runbooks that cut manual effort and improve deployment readiness in on-call environments. Practical AWS experience through personal labs and automation projects; experienced mentoring junior engineers on troubleshooting and operational best practices.',
    skills: ['Incident Management','On-Call / Rotational Support','Root Cause Analysis','Problem Management','SOPs & Runbooks','Python','Bash','SQL','PL/SQL','Linux / Unix','REST APIs','JSON','Postman','Oracle Database','Control-M','ServiceNow','Salesforce','Git','Bitbucket','Change Management','Mentoring'],
    factset: [
      'Delivered L2 production support for enterprise Workforce Management applications across Oracle databases and Linux servers, maintaining high availability of business-critical systems.',
      'Triaged and resolved 8–10 production incidents daily (approximately 170–190/month), maintaining ~98.6% SLA compliance by prioritizing production-impacting issues and escalating early.',
      'Built Python automation for production health checks, log parsing, ServiceNow reporting, Control-M job validation, and release verification, cutting routine validation time from ~95 minutes to ~18 minutes per cycle.',
      'Performed advanced SQL troubleshooting, query optimization, execution plan analysis, and data reconciliation; monitored and troubleshot Linux servers through log and service analysis.',
      'Validated REST API integrations using Postman and Python across 12–15 production releases, including deployment validation, smoke testing, SQL verification, and post-release monitoring.',
      'Authored runbooks, SOPs, and troubleshooting guides; onboarded and mentored a new support engineer over approximately four months.',
      'Partnered with development, DBA, QA, and DevOps teams on root cause analysis and preventive fixes.'
    ],
    igt: [
      'Served as primary technical point of contact for reservation platform issues affecting global hotel operations.',
      'Automated operational reporting and data validation using Python, SQL, and Power Query; built Power BI dashboards tracking reservation accuracy and SLA compliance.',
      'Supported REST API testing between reservation and payment systems and participated in UAT for production releases; documented workflows and SOPs.',
      'Used Salesforce as a professional operational/work-management tool to view and monitor work items and update notes; not Salesforce administration or development.'
    ],
    concentrix: [
      'Diagnosed and resolved complex connectivity issues including TCP/IP, DNS, DHCP, Wi-Fi, VPN, and modem provisioning for broadband, voice, and networking services.',
      'Authored troubleshooting guides and knowledge-base articles and maintained CRM/ticketing workflows for support cases.'
    ],
    evidence: {
      python: 'confirmed professional use at FactSet and IGT',
      sql: 'confirmed professional use at FactSet and IGT',
      plsql: 'confirmed professional use at FactSet',
      linux: 'confirmed professional use at FactSet',
      unix: 'confirmed professional use at FactSet',
      oracle: 'confirmed professional use at FactSet',
      controlm: 'confirmed professional use at FactSet',
      servicenow: 'confirmed professional use at FactSet',
      rest: 'confirmed professional use at FactSet and IGT',
      json: 'confirmed professional use at FactSet',
      postman: 'confirmed professional use at FactSet',
      powerbi: 'confirmed professional use at IGT',
      powerquery: 'confirmed professional use at IGT',
      salesforce: 'confirmed professional operational/work-management use at IGT',
      aws: 'generic cloud/application-support experience is confirmed; EC2/IAM/S3/CloudWatch are self-directed unless separately confirmed',
      excel: 'UNCONFIRMED professional evidence — do not add as professional experience',
      advancedexcel: 'UNCONFIRMED — do not add',
      metrics: 'only use the quantitative metrics explicitly present in the canonical profile'
    }
  };

  const TERM_RULES = [
    ['Python','python','python scripting','automation'],
    ['SQL / PL/SQL','sql','pl/sql','oracle'],
    ['Linux / Unix','linux','unix'],
    ['REST APIs / JSON','rest api','restful','json','postman'],
    ['ServiceNow / ITSM','servicenow','itsm','incident management','ticket'],
    ['Control-M','control-m','control m','batch'],
    ['Power BI','power bi','powerbi','power-bi'],
    ['Power Query','power query'],
    ['Salesforce','salesforce'],
    ['AWS / Cloud','aws','cloud','ec2','iam','s3','cloudwatch'],
    ['Excel','excel','microsoft excel'],
    ['Advanced Excel','advanced excel','vba','macros','pivot tables'],
    ['SLA / incident operations','sla','incident','on-call','on call','root cause','rca']
  ];

  function normalize(s){ return String(s||'').toLowerCase().replace(/[^a-z0-9+#./ -]+/g,' ').replace(/\s+/g,' ').trim(); }
  function mentions(text, terms){ const n=normalize(text); return terms.some(t=>n.includes(normalize(t))); }
  function canonicalAllowed(label){
    const key=label.toLowerCase();
    return !['Excel','Advanced Excel'].includes(label) || PROFILE.evidence[key.replace(/[^a-z]/g,'')] === 'confirmed professional use';
  }

  function analyze(text){
    const found=[]; const gaps=[];
    TERM_RULES.forEach(([label,...terms]) => {
      if(!mentions(text,terms)) return;
      const evidenceKey = label.toLowerCase().replace(/[^a-z]/g,'');
      const evidence = PROFILE.evidence[evidenceKey];
      if(evidence && !evidence.startsWith('UNCONFIRMED')) found.push({label,evidence});
      else gaps.push({label,reason:evidence||'No authoritative evidence mapping found.'});
    });
    const requirements = [
      ['Support / troubleshooting', ['support','troubleshoot','technical support','production support','application support']],
      ['Incident management', ['incident','ticket','sla','service desk']],
      ['Databases / SQL', ['sql','oracle','database','pl/sql']],
      ['Linux / Unix', ['linux','unix']],
      ['APIs / integrations', ['rest api','api','json','postman']],
      ['Automation / scripting', ['python','automation','bash','scripting']],
      ['Cloud', ['aws','cloud','ec2','s3','cloudwatch']]
    ];
    let applicable=0, matched=0;
    requirements.forEach(([label,terms])=>{ if(mentions(text,terms)){ applicable++; if(found.some(x=>x.label===label || mentions(x.label,terms))) matched++; }});
    const skillScore = applicable ? Math.round((matched/applicable)*100) : 0;
    const strong = Math.min(100, Math.round(skillScore*0.75 + (found.length ? Math.min(found.length*4,25) : 0)));
    return {found,gaps,score:strong,applicable,matched};
  }

  function renderFit(result){
    const badge=$('#fitBadge'); badge.textContent=`${result.score}% FIT`; badge.className=`pill ${result.score>=80?'green':result.score>=65?'warning':'red'}`;
    $('#fitResult').innerHTML=`<div class="copilot-score"><strong>${result.score}%</strong><span>evidence-aware fit</span></div><p>${result.score>=80?'Strong match. Review the remaining gaps before applying.':result.score>=65?'Defensible match with gaps. Review mandatory requirements manually.':'Weak match. Do not force the resume to match unsupported requirements.'}</p><p class="muted">Matched ${result.matched} of ${result.applicable || 0} applicable role-family requirement groups. This is a screening aid, not an ATS score.</p>`;
    $('#gapList').innerHTML=`<div class="copilot-gaps"><h4>Evidence boundaries</h4>${result.gaps.length?result.gaps.map(g=>`<div class="gap"><strong>${E(g.label)}</strong><span>${E(g.reason)}</span></div>`).join(''):'<div class="gap good"><strong>No mapped unsupported skills detected</strong><span>Continue checking education, location, seniority, and mandatory questions manually.</span></div>'}</div>`;
  }

  function tailoredResume(company,title,result){
    const text=normalize($('#jobText').value);
    const relevantSkills=[];
    PROFILE.skills.forEach(s=>{
      const n=normalize(s);
      if(text.includes(n) || (s==='Incident Management' && mentions(text,['incident','ticket','support'])) || (s==='Python' && mentions(text,['python','automation'])) || (s==='SQL' && mentions(text,['sql','database','oracle'])) || (s==='Linux / Unix' && mentions(text,['linux','unix']))) relevantSkills.push(s);
    });
    const safeSkills=[...new Set(relevantSkills)].filter(s=>!['Excel'].includes(s));
    const summary=result.score>=80
      ? `Production support engineer with nearly 3 years of experience supporting enterprise systems, incident response, RCA, SLA-driven operations, SQL/Oracle troubleshooting, Linux/Unix support, REST API validation and Python automation. Experienced with production releases, runbooks, cross-functional escalation and 24/7 operational environments.`
      : PROFILE.summary;
    const skills=safeSkills.length?safeSkills:PROFILE.skills.filter(s=>!['Excel'].includes(s)).slice(0,12);
    const html=`<article class="resume-doc"><header><h1>${E(PROFILE.name)}</h1><p>${E(PROFILE.location)} · ${E(company||'Target employer')} · ${E(title||'Target role')}</p></header><section><h4>PROFESSIONAL SUMMARY</h4><p>${E(summary)}</p></section><section><h4>CORE SKILLS</h4><p>${skills.map(E).join(' · ')}</p></section><section><h4>PROFESSIONAL EXPERIENCE</h4><h5>Product Support Engineer — FactSet Systems <span>Nov 2024 – Jan 2026</span></h5><ul>${PROFILE.factset.map(x=>`<li>${E(x)}</li>`).join('')}</ul><h5>Technical Operations Analyst — IGT Solutions <span>Dec 2023 – May 2024</span></h5><ul>${PROFILE.igt.map(x=>`<li>${E(x)}</li>`).join('')}</ul><h5>Technical Support Representative — Concentrix (Comcast) <span>Nov 2021 – Oct 2022</span></h5><ul>${PROFILE.concentrix.map(x=>`<li>${E(x)}</li>`).join('')}</ul></section><section><h4>EDUCATION</h4><p>${E(PROFILE.education)}</p></section><section class="resume-note"><strong>Truth Guard note:</strong> ${E(result.gaps.length?'JD-specific unsupported requirements remain outside the resume.':'No mapped unsupported skills were added.')}</section></article>`;
    $('#resumePreview').innerHTML=html;
    $('#printResume').disabled=false;
    $('#applyJob').disabled=!Boolean($('#copilotUrl').value.trim());
  }

  function init(){
    if(!$('#analyzeJob')) return;
    $('#analyzeJob').addEventListener('click',()=>{
      const text=$('#jobText').value.trim();
      if(!text){ $('#copilotMessage').textContent='Paste a job description first.'; return; }
      const result=analyze(text); window.__careerPilotAnalysis=result;
      renderFit(result); $('#generateResume').disabled=false; $('#copilotMessage').textContent='Analysis complete. Unsupported skills are kept outside the resume.';
    });
    $('#generateResume').addEventListener('click',()=>{
      const result=window.__careerPilotAnalysis; if(!result) return;
      tailoredResume($('#copilotCompany').value.trim(),$('#copilotTitle').value.trim(),result);
    });
    $('#printResume').addEventListener('click',()=>window.print());
    $('#applyJob').addEventListener('click',()=>{ const url=$('#copilotUrl').value.trim(); if(url) window.open(url,'_blank','noopener'); });
    $('#clearJob').addEventListener('click',()=>{ ['copilotCompany','copilotTitle','copilotUrl','jobText'].forEach(id=>{const el=$('#'+id); if(el) el.value='';}); $('#fitBadge').textContent='NOT ANALYZED'; $('#fitBadge').className='pill warning'; $('#fitResult').innerHTML='<p class="muted">Paste a job description and select Analyze fit.</p>'; $('#gapList').innerHTML=''; $('#resumePreview').innerHTML='<p class="muted">Your tailored resume will appear here after analysis.</p>'; $('#generateResume').disabled=true; $('#printResume').disabled=true; $('#applyJob').disabled=true; });
    $('#copilotUrl').addEventListener('input',()=>{ if(window.__careerPilotAnalysis) $('#applyJob').disabled=!Boolean($('#copilotUrl').value.trim()); });
    const canonical=$('#canonicalResume');
    if(canonical) canonical.innerHTML=`<div class="resume-preview"><article class="resume-doc"><header><h1>${E(PROFILE.name)}</h1><p>${E(PROFILE.location)}</p></header><section><h4>PROFESSIONAL SUMMARY</h4><p>${E(PROFILE.summary)}</p></section><section><h4>CORE SKILLS</h4><p>${PROFILE.skills.map(E).join(' · ')}</p></section><section><h4>EXPERIENCE</h4><h5>Product Support Engineer — FactSet Systems <span>Nov 2024 – Jan 2026</span></h5><ul>${PROFILE.factset.map(x=>`<li>${E(x)}</li>`).join('')}</ul><h5>Technical Operations Analyst — IGT Solutions <span>Dec 2023 – May 2024</span></h5><ul>${PROFILE.igt.map(x=>`<li>${E(x)}</li>`).join('')}</ul><h5>Technical Support Representative — Concentrix (Comcast) <span>Nov 2021 – Oct 2022</span></h5><ul>${PROFILE.concentrix.map(x=>`<li>${E(x)}</li>`).join('')}</ul></section><section><h4>EDUCATION</h4><p>${E(PROFILE.education)}</p></section></article></div>`;
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init); else init();
})();
