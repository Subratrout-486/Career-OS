/* Small presentation adapter: lets a durable job record feed the Job Copilot. */
(() => {
  const $ = s => document.querySelector(s);
  const wire = () => {
    const table = $('#jobsTable'); if(!table) return;
    table.querySelectorAll('tbody tr').forEach(row => {
      if(row.dataset.copilotWired || !row.children.length) return;
      const cells = row.children;
      const titleLink = row.querySelector('a.record-link');
      const title = titleLink?.textContent?.replace(/\s*↗\s*$/,'').trim() || cells[0]?.textContent?.split('\n').pop()?.trim();
      const company = cells[0]?.querySelector('strong')?.textContent?.trim() || '';
      const url = titleLink?.href || '';
      const actionCell = document.createElement('td');
      actionCell.innerHTML = `<button class="secondary capture-job" type="button">Analyze</button>`;
      row.appendChild(actionCell); row.dataset.copilotWired='1';
      actionCell.querySelector('button').addEventListener('click',()=>{
        const nav=document.querySelector('.nav[data-view="copilot"]'); if(nav) nav.click();
        setTimeout(()=>{
          const titleInput=$('#copilotTitle'), companyInput=$('#copilotCompany'), urlInput=$('#copilotUrl');
          if(titleInput) titleInput.value=title || '';
          if(companyInput) companyInput.value=company || '';
          if(urlInput) urlInput.value=url || '';
          const msg=$('#copilotMessage'); if(msg) msg.textContent='Job captured. Paste the full JD below to run the evidence-aware assessment.';
        },0);
      });
    });
  };
  const titleMap={overview:'CareerPilot control center',copilot:'Job Copilot — analyze, tailor, apply',jobs:'Job pipeline',applications:'Applications',resumes:'Resume Center',review:'Needs Review',health:'Health status',agents:'System components',profile:'Profile & resume'};
  const updateTitle=()=>{const active=document.querySelector('.view.active-view'); const title=titleMap[active?.id]; if(title&&$('#pageTitle')) $('#pageTitle').textContent=title;};
  const observer=new MutationObserver(()=>{wire();updateTitle();});
  const start=()=>{wire();updateTitle();observer.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['class']}); document.querySelectorAll('.nav').forEach(b=>b.addEventListener('click',()=>setTimeout(updateTitle,0)));};
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',start); else start();
})();
