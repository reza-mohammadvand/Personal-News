const state={articles:[],topic:'all',source:'all',days:1,query:'',shown:12};
const $=s=>document.querySelector(s); const fa=n=>Number(n).toLocaleString('fa-IR');
const topicNames={technology:'فناوری',space:'فضا و نجوم',economy:'اقتصاد',science:'علم و سلامت',marvel:'مارول',gaming:'بازی و سرگرمی',politics:'سیاست و جهان',other:'سایر'};
const priorityNames={3:'اولویت بالا',2:'اولویت متوسط',1:'اولویت عادی'};

function esc(v=''){const d=document.createElement('div');d.textContent=v;return d.innerHTML}
function relativeDate(value){const diff=Date.now()-new Date(value).getTime(),h=Math.max(0,Math.floor(diff/36e5));if(h<1)return'همین حالا';if(h<24)return`${fa(h)} ساعت پیش`;return`${fa(Math.floor(h/24))} روز پیش`}
function render(){
 const filtered=state.articles.filter(a=>{const age=(Date.now()-new Date(a.published).getTime())/864e5;const text=`${a.title} ${a.summary} ${(a.tags||[]).join(' ')}`.toLowerCase();return age<=state.days+.25&&(state.source==='all'||a.source===state.source)&&(state.topic==='all'||a.topic===state.topic)&&(!state.query||text.includes(state.query.toLowerCase()))}).sort((a,b)=>(b.priority||0)-(a.priority||0)||new Date(b.published)-new Date(a.published));
 $('#resultCount').textContent=`${fa(filtered.length)} خبر`;$('#emptyState').classList.toggle('hidden',filtered.length>0);$('#newsGrid').innerHTML=filtered.slice(0,state.shown).map(card).join('');$('#loadMore').classList.toggle('hidden',filtered.length<=state.shown);
}
function card(a){const level=Math.max(1,a.priority||1);const tags=(a.tags||[topicNames[a.topic]]).slice(0,3).map(t=>`<span class="tag">${esc(t)}</span>`).join('');const media=a.image?`<img class="card-image" src="${esc(a.image)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.outerHTML='<div class=&quot;image-fallback&quot;>◌</div>'">`:`<div class="image-fallback">◌</div>`;return`<article class="card">${media}<div class="card-body"><div class="meta"><span class="source">${esc(a.source)}</span><time datetime="${esc(a.published)}">${relativeDate(a.published)}</time></div><h3>${esc(a.title)}</h3><p class="summary">${esc(a.summary||'برای مطالعه توضیحات کامل، وارد منبع اصلی خبر شوید.')}</p><div class="tags"><span class="priority-badge priority-${level}">${priorityNames[level]}</span>${tags}</div><a class="card-link" href="${esc(a.link)}" target="_blank" rel="noopener noreferrer">مطالعه در منبع اصلی <span>←</span></a></div></article>`}
function bind(){
 $('#daysSelect').onchange=e=>{state.days=+e.target.value;state.shown=12;render()};$('#sourceSelect').onchange=e=>{state.source=e.target.value;render()};$('#searchInput').oninput=e=>{state.query=e.target.value.trim();render()};
 $('#topicTabs').onclick=e=>{const b=e.target.closest('[data-topic]');if(!b)return;document.querySelectorAll('.topic').forEach(x=>x.classList.remove('active'));b.classList.add('active');state.topic=b.dataset.topic;state.shown=12;render()};
 $('#loadMore').onclick=()=>{state.shown+=12;render()};$('#refreshButton').onclick=()=>load(true);$('#themeButton').onclick=()=>{document.body.classList.toggle('light');localStorage.setItem('theme',document.body.classList.contains('light')?'light':'dark')};
}
async function load(fresh=false){
 $('#newsGrid').innerHTML='<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>';$('#errorState').classList.add('hidden');
 try{const res=await fetch(`data/news.json${fresh?'?t='+Date.now():''}`);if(!res.ok)throw Error();const data=await res.json();state.articles=data.articles||[];const sources=Object.keys(data.sources||{}).length?Object.keys(data.sources):[...new Set(state.articles.map(a=>a.source))];sources.sort();$('#sourceSelect').innerHTML='<option value="all">همه منابع</option>'+sources.map(s=>`<option>${esc(s)}</option>`).join('');$('#updateLabel').innerHTML=`<i></i> آخرین بروزرسانی: ${new Date(data.updated_at).toLocaleString('fa-IR',{dateStyle:'short',timeStyle:'short'})}`;render()}catch{$('#newsGrid').innerHTML='';$('#errorState').classList.remove('hidden');$('#resultCount').textContent='۰ خبر'}
}
if(localStorage.getItem('theme')==='light')document.body.classList.add('light');bind();load();
