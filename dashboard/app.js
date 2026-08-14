const DEMO={
  meta:{last_sync:null,source:'demo'},
  stats:{new_jobs:12,strong_matches:6,resumes:5,auto_applied:0,needs_review:3},
  jobs:[
    {company:'TCS',title:'Service Desk Associate (L1)',location:'Hyderabad',fit:88,ats:100,status:'REVIEW_REQUIRED',reason:'Mandatory question requires approved answer',source:'LinkedIn'},
    {company:'Anblicks',title:'Technical Support Analyst I',location:'Hyderabad',fit:82,ats:100,status:'REVIEW_REQUIRED',reason:'On-site / 24×7 confirmation',source:'LinkedIn'},
    {company:'HighRadius',title:'Product Support Engineer',location:'Hyderabad',fit:84,ats:100,status:'READY',reason:'Tailored resume available',source:'Greenhouse'}
  ],
  applications:[
    {company:'TCS',title:'Service Desk Associate (L1)',status:'Review',fit:88,ats:100,reason:'Engineering-experience question'},
    {company:'Anblicks',title:'Technical Support Analyst I',status:'Review',fit:82,ats:100,reason:'On-site / shift confirmation'}
  ],
  resumes:[
    {company:'TCS',title:'Service Desk Associate (L1)',ats:100,truth:'PASS',files:'PDF + DOCX'},
    {company:'Anblicks',title:'Technical Support Analyst I',ats:100,truth:'PASS',files:'PDF + DOCX'},
    {company:'HighRadius',title:'Product Support Engineer',ats:100,truth:'PASS',files:'PDF + DOCX'}
  ],
  reviews:[
    {company:'TCS',title:'Service Desk Associate (L1)',reason:'Required: engineering experience. Approved answer for this specific question: 0 years.'},
    {company:'Anblicks',title:'Technical Support Analyst I',reason:'Confirm Hyderabad on-site and 24×7 rotational availability.'},
    {company:'Salary',title:'Compensation question',reason:'Salary/CTC remains user-controlled.'}
  ],
  agents:[
    ['JD Analyzer','Decomposes each JD into requirements.'],['Evidence Retrieval','Pulls only verified career evidence.'],['Fit Agent','Scores fit, gaps and risks.'],['Resume Agent','Creates the JD-specific one-page resume.'],['Truth Guard','Blocks unsupported claims.'],['ATS Auditor','Measures keyword coverage.'],['Grok Challenger','Independent adversarial review when configured.'],['Application Executor','Browser upload, form inspection and submission gates.'],['Notion Writer','Persists Jobs, Resume Library and Applications state.']
  ],
  profile:[['Current location','Hyderabad, India'],['On-site / hybrid','Yes'],['Relocation within India','Yes'],['24×7 / rotational / EMEA / night','Yes'],['Work authorization','Authorized to work in India; no employer sponsorship required'],['Sponsorship','No'],['Notice period','Immediate / 0 days'],['Salary / CTC','Ask me each time']]
};
let DATA=DEMO;
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const scoreClass=n=>n>=85?'good':n>=70?'mid':'';
function show(view){document.querySelectorAll('.view').forEach(x=>x.classList.remove('active-view'));$('#'+view).classList.add('active-view');document.querySelectorAll('.nav').forEach(x=>x.classList.toggle('active',x.dataset.view===view));const titles={overview:'Good morning, Subrat',jobs:'Job pipeline',applications:'Applications',resumes:'Resume Center',review:'Needs Review',agents:'AI Agents',profile:'Profile & rules'};$('#pageTitle').textContent=titles[view]||'Career OS';}
function status(s){const x=String(s||'').toLowerCase();let c=x.includes('submitted')?'submitted':x.includes('review')?'review':x.includes('blocked')?'blocked':'ready';return `<span class="status ${c}">${esc(s||'Ready')}</span>`}
function render(){
  const st=DATA.stats||{};const labels=[['New jobs found',st.new_jobs||0,'discovered'],['Strong matches',st.strong_matches||0,'fit-qualified'],['Resumes generated',st.resumes||0,'JD-specific'],['Auto-applied',st.auto_applied||0,'verified submissions'],['Needs review',st.needs_review||0,'your attention']];
  $('#stats').innerHTML=labels.map(x=>`<div class="stat"><div class="label">${x[0]}</div><div class="value">${x[1]}</div><div class="delta">${x[2]}</div></div>`).join('');
  $('#reviewBadge').textContent=st.needs_review||0;
  $('#priorityJobs').innerHTML=(DATA.jobs||[]).slice(0,5).map(j=>`<div class="job-row"><div><div class="job-title">${esc(j.company)} — ${esc(j.title)}</div><div class="job-meta">${esc(j.location)} · ${esc(j.source||'Career OS')}</div></div><div><div class="score ${scoreClass(j.fit)}">${j.fit}% fit</div>${status(j.status)}</div></div>`).join('')||'<p class="muted">No jobs yet.</p>';
  $('#reviewList').innerHTML=(DATA.reviews||[]).slice(0,4).map(r=>`<div class="review-row"><div><div class="job-title">${esc(r.company)} — ${esc(r.title)}</div><div class="job-meta">${esc(r.reason)}</div></div>${status('Review')}</div>`).join('')||'<p class="muted">Nothing needs you.</p>';
  $('#agentStrip').innerHTML=(DATA.agents||[]).slice(0,5).map(a=>`<div class="agent"><span class="dot"></span><h4>${esc(a[0])}</h4><p>${esc(a[1])}</p></div>`).join('');
  renderJobs();renderApps();renderResumes();renderReviews();renderAgents();renderProfile();
  $('#lastSync').textContent=DATA.meta?.last_sync?`Last sync: ${new Date(DATA.meta.last_sync).toLocaleString()}`:'Data: demo fallback';
}
function renderJobs(){const q=($('#jobSearch')?.value||'').toLowerCase();const rows=(DATA.jobs||[]).filter(j=>`${j.company} ${j.title}`.toLowerCase().includes(q));$('#jobsTable').innerHTML=`<table class="table"><thead><tr><th>Role</th><th>Location</th><th>Fit</th><th>ATS</th><th>Status</th><th>Reason</th></tr></thead><tbody>${rows.map(j=>`<tr><td><strong>${esc(j.company)}</strong><br>${esc(j.title)}</td><td>${esc(j.location)}</td><td class="score ${scoreClass(j.fit)}">${j.fit}%</td><td>${j.ats??'—'}%</td><td>${status(j.status)}</td><td class="muted">${esc(j.reason||'')}</td></tr>`).join('')}</tbody></table>`}
function renderApps(){$('#appsTable').innerHTML=`<table class="table"><thead><tr><th>Company / role</th><th>Fit</th><th>ATS</th><th>Status</th><th>Next action</th></tr></thead><tbody>${(DATA.applications||[]).map(a=>`<tr><td><strong>${esc(a.company)}</strong><br>${esc(a.title)}</td><td>${a.fit}%</td><td>${a.ats}%</td><td>${status(a.status)}</td><td class="muted">${esc(a.reason||'')}</td></tr>`).join('')}</tbody></table>`}
function renderResumes(){$('#resumeTable').innerHTML=`<table class="table"><thead><tr><th>Target</th><th>ATS</th><th>Truth Guard</th><th>Files</th></tr></thead><tbody>${(DATA.resumes||[]).map(r=>`<tr><td><strong>${esc(r.company)}</strong><br>${esc(r.title)}</td><td>${r.ats}%</td><td>${status(r.truth)}</td><td>${esc(r.files)}</td></tr>`).join('')}</tbody></table>`}
function renderReviews(){$('#reviewCards').innerHTML=(DATA.reviews||[]).map(r=>`<div class="review-card"><h3>${esc(r.company)} — ${esc(r.title)}</h3><p>${esc(r.reason)}</p><p><button class="secondary" onclick="alert('Open the linked application/review record from Notion or GitHub Actions.')">Open review</button></p></div>`).join('')||'<div class="card"><h3>All clear</h3><p class="muted">Nothing needs your attention.</p></div>'}
function renderAgents(){$('#agentsGrid').innerHTML=(DATA.agents||[]).map(a=>`<div class="agent-large"><span class="pill green">ACTIVE ROLE</span><h3>${esc(a[0])}</h3><p>${esc(a[1])}</p></div>`).join('')}
function renderProfile(){$('#profileGrid').innerHTML=(DATA.profile||[]).map(p=>`<div class="profile-item"><div class="k">${esc(p[0])}</div><div class="v">${esc(p[1])}</div></div>`).join('')}
async function load(){try{const r=await fetch('data.json?'+Date.now(),{cache:'no-store'});if(r.ok){const live=await r.json();DATA={...DEMO,...live,stats:{...DEMO.stats,...live.stats}}}}catch(e){}render()}
document.querySelectorAll('.nav').forEach(b=>b.addEventListener('click',()=>show(b.dataset.view)));document.querySelectorAll('[data-view-jump]').forEach(b=>b.addEventListener('click',()=>show(b.dataset.viewJump)));$('#refresh').addEventListener('click',load);$('#jobSearch').addEventListener('input',renderJobs);load();
