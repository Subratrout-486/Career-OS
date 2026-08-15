const COMPONENTS=[
  ['JD Analyzer','Decomposes each verified job description into role requirements.'],
  ['Evidence Retrieval','Uses durable career evidence for matching and tailoring.'],
  ['Fit Agent','Scores fit, gaps, and risk from the recorded job data.'],
  ['Resume Agent','Generates JD-specific artifacts only after the required gates pass.'],
  ['Truth Guard','Blocks unsupported claims before an application can proceed.'],
  ['ATS Auditor','Records keyword-coverage analysis for the generated resume.'],
  ['Recruiter Review','Records the independent review required by the pipeline.'],
  ['Application Executor','Runs preflight, exact-resume verification, and confirmation reconciliation.'],
  ['Notion Writer','Persists durable jobs, resumes, applications, evidence, and blockers.']
];

const PROFILE=[
  ['Current location','Hyderabad, India'],
  ['On-site / hybrid','Yes'],
  ['Relocation within India','Yes'],
  ['24×7 / rotational / EMEA / night','Yes'],
  ['Work authorization','Authorized to work in India; no employer sponsorship required'],
  ['Sponsorship','No'],
  ['Notice period','Immediate / 0 days'],
  ['Salary / CTC','Ask me each time']
];

const EXECUTION_STATES=[
  ['ready','Ready','ready, auto_apply, auto-apply, ready to apply'],
  ['waiting','Waiting for execution','waiting, queued, saved, researching, draft'],
  ['dispatched','Dispatched','dispatched, dispatching'],
  ['running','Manus running','running, manus running, in progress'],
  ['submitted','Submitted','submitted, applied'],
  ['verified','Verified','verified, confirmed, authoritative confirmation'],
  ['review','Review required','review, review required, under review, question'],
  ['blocked','Blocked','blocked, do not apply, do_not_apply'],
  ['failed','Failed','failed, error'],
  ['duplicate','Duplicate','duplicate']
];

const EMPTY={
  meta:{
    last_sync:null,
    source:'unavailable',
    status:'NOTION_SYNC_BLOCKED',
    message:'No authoritative Career OS dashboard snapshot is available.'
  },
  stats:{new_jobs:0,strong_matches:0,resumes:0,auto_applied:0,needs_review:0},
  jobs:[],applications:[],resumes:[],reviews:[],
  health:{
    notion:{state:'NOTION_SYNC_BLOCKED',detail:'No completed Notion snapshot is available.'},
    github:{state:'NOT_CHECKED',detail:'No GitHub Actions health evidence is available.'},
    pipeline:{state:'NOT_CHECKED',detail:'No pipeline health evidence is available.'},
    manus:{state:'NOT_CHECKED',detail:'No verified browser-execution evidence is available.'}
  }
};

let DATA=EMPTY;
let CONTROL_PLANE=null;
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number=v=>Number.isFinite(Number(v))?Number(v):0;
const scoreClass=n=>number(n)>=85?'good':number(n)>=70?'mid':'';
const rowOrEmpty=(colspan,message)=>`<tr><td class="muted" colspan="${colspan}">${esc(message)}</td></tr>`;
const normalized=s=>String(s??'').trim().toLowerCase().replace(/[_-]+/g,' ');

function isAuthoritative(data){
  return data?.meta?.source==='notion' && Boolean(data?.meta?.last_sync);
}

function isStale(data){
  if(!isAuthoritative(data)) return false;
  const synced=Date.parse(data.meta.last_sync);
  return Number.isFinite(synced) && Date.now()-synced>3*60*60*1000;
}

function safeUrl(value){
  try{
    const url=new URL(String(value||''));
    return ['http:','https:'].includes(url.protocol)?url.href:null;
  }catch{return null;}
}

function stateKey(value){
  const valueNormalized=normalized(value);
  const match=EXECUTION_STATES.find(([, , aliases])=>aliases.split(', ').some(alias=>valueNormalized===alias));
  return match?.[0]||'other';
}

function stateLabel(value){
  const key=stateKey(value);
  return EXECUTION_STATES.find(([candidate])=>candidate===key)?.[1]||String(value||'Not recorded');
}

function status(value){
  const label=String(value||'NOT_RECORDED');
  const kind=stateKey(label);
  return `<span class="status ${kind}">${esc(label)}</span>`;
}

function healthStatus(value){
  const state=String(value?.state||'NOT_CHECKED');
  return `<div class="job-row"><div><div class="job-title">${esc(state.replaceAll('_',' '))}</div><div class="job-meta">${esc(value?.detail||'No detail recorded.')}</div></div>${status(state)}</div>`;
}

function show(view){
  document.querySelectorAll('.view').forEach(x=>x.classList.remove('active-view'));
  $('#'+view).classList.add('active-view');
  document.querySelectorAll('.nav').forEach(x=>x.classList.toggle('active',x.dataset.view===view));
  const titles={overview:'Career OS control center',jobs:'Job pipeline',applications:'Applications',resumes:'Resume Center',review:'Needs Review',health:'Health status',agents:'System components',profile:'Profile & rules'};
  $('#pageTitle').textContent=titles[view]||'Career OS';
}

function renderSystemState(){
  const authoritative=isAuthoritative(DATA);
  const stale=isStale(DATA);
  const controlPlaneConnected=Boolean(CONTROL_PLANE);
  const mode=authoritative?(stale?'STALE SNAPSHOT':'AUTHORITATIVE DATA'):(controlPlaneConnected?'CONTROL PLANE CONNECTED':'SYNC BLOCKED');
  const description=authoritative
    ?(stale?'The dashboard snapshot is older than three hours; inspect GitHub Actions before relying on it.':'The dashboard is showing the latest completed Notion snapshot.')
    :(controlPlaneConnected?'The cloud control plane is connected. Job/application facts remain unavailable until an authoritative snapshot is present.':(DATA.meta?.message||'No authoritative backend data is available.'));
  $('#liveStatus').textContent=authoritative&&!stale?'Live data':stale?'Stale data':controlPlaneConnected?'Control plane connected':'Data unavailable';
  $('#liveStatus').className=`live ${authoritative&&!stale||controlPlaneConnected?'healthy':'blocked'}`;
  $('#automationPill').textContent=mode;
  $('#automationPill').className=`pill ${authoritative&&!stale||controlPlaneConnected?'green':'warning'}`;
  $('#systemStatus').textContent=authoritative&&!stale?'Authoritative snapshot connected':stale?'Snapshot is stale':controlPlaneConnected?'Cloud control plane connected':'Authoritative snapshot unavailable';
  $('#systemStatus').className=authoritative&&!stale||controlPlaneConnected?'system healthy':'system blocked';
  $('#dataNotice').textContent=description;
  $('#lastSync').textContent=authoritative
    ?`Last Notion sync: ${new Date(DATA.meta.last_sync).toLocaleString()}${stale?' (stale)':''}`
    :controlPlaneConnected?'Control plane API connected — job records are not inferred.':'Notion sync blocked — no dashboard state is inferred.';
}

function executionRecords(){
  return (DATA.applications||[]).filter(row=>String(row.status||'').trim());
}

function statusCounts(){
  const counts=Object.fromEntries(EXECUTION_STATES.map(([key])=>[key,0]));
  let other=0;
  executionRecords().forEach(row=>{
    const key=stateKey(row.status);
    if(key in counts) counts[key]+=1; else other+=1;
  });
  return {counts,other,total:executionRecords().length};
}

function renderStatusSummary(){
  const {counts,other,total}=statusCounts();
  $('#statusSummary').innerHTML=EXECUTION_STATES.map(([key,label])=>`<div class="status-metric ${key}"><div class="status-metric-label">${esc(label)}</div><div class="status-metric-value">${counts[key]}</div><div class="status-metric-note">recorded applications</div></div>`).join('')+`<div class="status-metric other"><div class="status-metric-label">Other recorded</div><div class="status-metric-value">${other}</div><div class="status-metric-note">unmapped application states</div></div>`;
  $('#statusSummaryNote').textContent=total?`${total} application records are included. Counts are read from the authoritative snapshot and are not inferred from workflow completion.`:'No application execution records are available in the current snapshot.';
}

function renderControlPlane(){
  const tasks=CONTROL_PLANE?.tasks||[];
  const approvals=CONTROL_PLANE?.approvals||[];
  const pending=approvals.filter(item=>item.status==='PENDING').length;
  const failed=tasks.filter(item=>['FAILED','BLOCKED'].includes(item.status)).length;
  const usage=(CONTROL_PLANE?.usage||[]).reduce((sum,item)=>sum+number(item.credits),0);
  const metrics=[
    ['Tasks',tasks.length,'durable objectives'],
    ['Pending approvals',pending,'human decisions'],
    ['Failures / blocks',failed,'explicit exceptions'],
    ['Recorded credits',usage.toFixed(2),'usage events']
  ];
  $('#controlPlaneSummary').innerHTML=metrics.map(item=>`<div class="status-metric ${item[1]?'mid':'ready'}"><div class="status-metric-label">${esc(item[0])}</div><div class="status-metric-value">${esc(item[1])}</div><div class="status-metric-note">${esc(item[2])}</div></div>`).join('');
  $('#controlPlaneNote').textContent=CONTROL_PLANE
    ?`${tasks.length} task records, ${approvals.length} approval records, and ${(CONTROL_PLANE.agents||[]).length} registered agents are available from the durable control plane.`
    :'The browser API is not connected. The static dashboard remains available as a read-only snapshot.';
}

function render(){
  const st=DATA.stats||{};
  const labels=[
    ['New jobs found',number(st.new_jobs),'durable job records'],
    ['Strong matches',number(st.strong_matches),'fit-qualified records'],
    ['Resumes generated',number(st.resumes),'resume-library records'],
    ['Applied',number(st.auto_applied),'authoritative confirmations'],
    ['Needs review',number(st.needs_review),'recorded exceptions']
  ];
  $('#stats').innerHTML=labels.map(x=>`<div class="stat"><div class="label">${x[0]}</div><div class="value">${x[1]}</div><div class="delta">${x[2]}</div></div>`).join('');
  $('#reviewBadge').textContent=number(st.needs_review);
  $('#priorityJobs').innerHTML=(DATA.jobs||[]).slice(0,5).map(j=>`<div class="job-row"><div><div class="job-title">${esc(j.company||'Company not recorded')} — ${esc(j.title||'Role not recorded')}</div><div class="job-meta">${esc(j.location||'Location not recorded')} · ${esc(j.source||'Source not recorded')}</div></div><div><div class="score ${scoreClass(j.fit)}">${j.fit==null?'—':number(j.fit)+'%'} fit</div>${status(j.status)}</div></div>`).join('')||'<p class="muted">No authoritative job records are available.</p>';
  $('#reviewList').innerHTML=(DATA.reviews||[]).slice(0,4).map(r=>`<div class="review-row"><div><div class="job-title">${esc(r.company||'Company not recorded')} — ${esc(r.title||'Role not recorded')}</div><div class="job-meta">${esc(r.reason||'No blocker detail recorded.')}</div></div>${status('REVIEW_REQUIRED')}</div>`).join('')||'<p class="muted">No recorded review exceptions.</p>';
  $('#healthList').innerHTML=['notion','github','pipeline','manus'].map(key=>healthStatus(DATA.health?.[key])).join('');
  $('#agentStrip').innerHTML=COMPONENTS.slice(0,5).map(a=>`<div class="agent"><span class="dot"></span><h4>${esc(a[0])}</h4><p>${esc(a[1])}</p></div>`).join('');
  renderStatusSummary();
  renderControlPlane();
  renderJobs();renderApps();renderResumes();renderReviews();renderAgents();renderProfile();renderSystemState();
}

function renderJobs(){
  const q=($('#jobSearch')?.value||'').toLowerCase();
  const rows=(DATA.jobs||[]).filter(j=>`${j.company||''} ${j.title||''}`.toLowerCase().includes(q));
  $('#jobsTable').innerHTML=`<table class="table"><thead><tr><th>Role</th><th>Location</th><th>Fit</th><th>ATS</th><th>Status</th><th>Reason</th></tr></thead><tbody>${rows.length?rows.map(j=>{const link=safeUrl(j.url); const role=link?`<a class="record-link" href="${esc(link)}" target="_blank" rel="noopener">${esc(j.title||'Role not recorded')} ↗</a>`:esc(j.title||'Role not recorded'); return `<tr><td><strong>${esc(j.company||'Company not recorded')}</strong><br>${role}</td><td>${esc(j.location||'—')}</td><td class="score ${scoreClass(j.fit)}">${j.fit==null?'—':number(j.fit)+'%'}</td><td>${j.ats==null?'—':number(j.ats)+'%'}</td><td>${status(j.status)}</td><td class="muted">${esc(j.reason||'—')}</td></tr>`;}).join(''):rowOrEmpty(6,'No authoritative job records match this view.')}</tbody></table>`;
}

function renderApps(){
  const rows=DATA.applications||[];
  $('#appsTable').innerHTML=`<table class="table"><thead><tr><th>Company / role</th><th>Fit</th><th>ATS</th><th>Execution state</th><th>Next action</th></tr></thead><tbody>${rows.length?rows.map(a=>`<tr><td><strong>${esc(a.company||'Company not recorded')}</strong><br>${esc(a.title||'Role not recorded')}</td><td>${a.fit==null?'—':number(a.fit)+'%'}</td><td>${a.ats==null?'—':number(a.ats)+'%'}</td><td>${status(a.status)}</td><td class="muted">${esc(a.reason||'—')}</td></tr>`).join(''):rowOrEmpty(5,'No authoritative application records are available.')}</tbody></table>`;
}

function renderResumes(){
  const rows=DATA.resumes||[];
  $('#resumeTable').innerHTML=`<table class="table"><thead><tr><th>Target</th><th>ATS</th><th>Truth Guard</th><th>Files</th></tr></thead><tbody>${rows.length?rows.map(r=>`<tr><td><strong>${esc(r.company||'Source job not recorded')}</strong><br>${esc(r.title||'Resume name not recorded')}</td><td>${r.ats==null?'—':number(r.ats)+'%'}</td><td>${status(r.truth)}</td><td>${esc(r.files||'Record only')}</td></tr>`).join(''):rowOrEmpty(4,'No authoritative resume-library records are available.')}</tbody></table>`;
}

function renderReviews(){
  const rows=DATA.reviews||[];
  $('#reviewCards').innerHTML=rows.length?rows.map(r=>`<div class="review-card"><h3>${esc(r.company||'Company not recorded')} — ${esc(r.title||'Role not recorded')}</h3><p>${esc(r.reason||'No blocker detail recorded.')}</p><p><a class="secondary" href="https://github.com/Subratrout-486/Career-OS/actions" target="_blank" rel="noopener">Open workflow evidence</a></p></div>`).join(''):'<div class="card"><h3>No recorded review exceptions</h3><p class="muted">The latest authoritative snapshot contains no application rows that are in review or blocked states.</p></div>';
}

function renderAgents(){
  $('#agentsGrid').innerHTML=COMPONENTS.map(a=>`<div class="agent-large"><span class="pill">COMPONENT</span><h3>${esc(a[0])}</h3><p>${esc(a[1])}</p></div>`).join('');
}

function renderProfile(){
  $('#profileGrid').innerHTML=PROFILE.map(p=>`<div class="profile-item"><div class="k">${esc(p[0])}</div><div class="v">${esc(p[1])}</div></div>`).join('');
}

async function load(){
  DATA=EMPTY;
  CONTROL_PLANE=null;
  try{
    const response=await fetch(`data.json?${Date.now()}`,{cache:'no-store'});
    if(!response.ok) throw new Error(`Snapshot request failed (${response.status}).`);
    const live=await response.json();
    if(!isAuthoritative(live)) throw new Error('Snapshot lacks authoritative Notion metadata.');
    DATA={...EMPTY,...live,stats:{...EMPTY.stats,...live.stats},health:{...EMPTY.health,...live.health}};
  }catch(error){
    DATA={...EMPTY,meta:{...EMPTY.meta,message:`${EMPTY.meta.message} ${error.message}`}};
  }
  try{
    const response=await fetch(`/api/dashboard?${Date.now()}`,{cache:'no-store'});
    if(response.ok) CONTROL_PLANE=await response.json();
  }catch(_error){
    CONTROL_PLANE=null;
  }
  render();
}

document.querySelectorAll('.nav').forEach(b=>b.addEventListener('click',()=>show(b.dataset.view)));
document.querySelectorAll('[data-view-jump]').forEach(b=>b.addEventListener('click',()=>show(b.dataset.viewJump)));
$('#refresh').addEventListener('click',load);
$('#jobSearch').addEventListener('input',renderJobs);
$('#objectiveForm').addEventListener('submit',async event=>{
  event.preventDefault();
  const input=$('#objectiveInput');
  const message=$('#objectiveMessage');
  const objective=input.value.trim();
  if(!objective) return;
  message.textContent='Queueing objective…';
  try{
    const response=await fetch('/api/objectives',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({objective})});
    const result=await response.json();
    if(!response.ok) throw new Error(result.detail||`Request failed (${response.status}).`);
    message.textContent=`Queued ${result.id}. The objective is durable and can be processed when an appropriate agent is available.`;
    input.value='';
    await load();
  }catch(error){
    message.textContent=`Objective was not queued: ${error.message}`;
  }
});
load();
