'use strict';
// Native UI inspired by the publicly inspectable OpenAlternative directory components.
const icon=(name,cls='')=>`<img class="ui-icon ${cls}" src="/icons/${name}.svg" alt="" width="20" height="20">`;
const discoveryCategories={all:['全部计划','layout-grid'],food:['饮食与备餐','salad'],move:['运动与活动','barbell'],rest:['睡眠与恢复','moon-stars'],mind:['心理与正念','brain'],habits:['日常习惯','clipboard-check'],learning:['博主学习','book-2'],tools:['专业工具','tools']};
let discoverCategory='all',discoverSort='recommended',discoverReady=true,discoverSaved=false,discoverLimit=18;
let planSaved=new Set();
try{const saved=JSON.parse(localStorage.getItem('baymax-plan-saved')||'[]');if(Array.isArray(saved))planSaved=new Set(saved.filter(x=>typeof x==='string'));}catch{}
function planCategory(m){if(m.kind==='learning'||m.kind==='creator')return 'learning';return ({food:'food',nutrition:'food',training:'move',outdoor:'move',sleep:'rest',mind:'mind',body:'habits',care:'tools',devices:'tools'})[m.category]||'habits';}
function planName(m){return m.title.replace(/ · (使用计划|资料评估)$/,'').replace(/^学习：/,'');}
function planKindName(m){return ({habit:'生活安排',tool:'工具使用',learning:'学习安排',creator:'作者计划',nutrition:'饮食计划',exercise:'活动计划'})[m.kind]||'计划';}
function planDuration(m){const days=new Set(m.actions.flatMap(a=>a.days||Array.from({length:30},(_,i)=>i+1)));return days.size===30?'每日安排':`${days.size} 个执行日`;}
function sortedPlans(){
 const preferred=['meal-preparation','gentle-movement','daily-reflection','weekly-review'];
 const text=lifeQuery.trim().toLocaleLowerCase();
 const list=lifeLibrary.modules.filter(m=>(lifeKind==='all'||m.kind===lifeKind)&&(discoverCategory==='all'||planCategory(m)===discoverCategory)&&(!discoverReady||m.status==='ready')&&(!discoverSaved||planSaved.has(m.id))&&[m.title,m.author,m.goal].join(' ').toLocaleLowerCase().includes(text));
 const rank=m=>preferred.includes(m.id)?preferred.indexOf(m.id):m.kind==='learning'?10:m.kind==='tool'?20:30;
 return list.sort((a,b)=>discoverSort==='name'?planName(a).localeCompare(planName(b),'zh-CN'):discoverSort==='steps'?a.actions.length-b.actions.length:rank(a)-rank(b));
}
function discoveryHash(){
 const q=new URLSearchParams();if(lifeQuery)q.set('q',lifeQuery);if(lifeKind!=='all')q.set('kind',lifeKind);if(discoverCategory!=='all')q.set('category',discoverCategory);if(discoverSort!=='recommended')q.set('sort',discoverSort);if(!discoverReady)q.set('drafts','1');if(discoverSaved)q.set('saved','1');
 return '#plans'+(q.size?'?'+q:'');
}
function restoreDiscovery(){
 const p=currentRoute().params;lifeQuery=p.get('q')||'';lifeKind=Object.hasOwn(lifeKinds,p.get('kind'))?p.get('kind'):'all';discoverCategory=Object.hasOwn(discoveryCategories,p.get('category'))?p.get('category'):'all';discoverSort=['name','steps'].includes(p.get('sort'))?p.get('sort'):'recommended';discoverReady=!p.has('drafts');discoverSaved=p.has('saved');discoverLimit=18;
}
function planCard(m){
 const selected=lifeCart.some(x=>x.module===m.id),category=planCategory(m);
 return `<article class="plan-card${selected?' is-selected':''}"><div class="plan-card-top"><a href="#plan?id=${m.id}" class="plan-symbol symbol-${category}" aria-label="查看 ${esc(planName(m))}">${icon(discoveryCategories[category][1])}</a><button class="plan-bookmark" data-plan-save="${m.id}" aria-label="${planSaved.has(m.id)?'取消收藏':'收藏'} ${esc(planName(m))}" aria-pressed="${planSaved.has(m.id)}">${icon('bookmark')}</button></div><h2><a href="#plan?id=${m.id}" data-life-detail="${m.id}">${esc(planName(m))}</a></h2><p class="plan-description">${esc(m.goal)}</p><div class="plan-author">${esc(m.author)}<span>${planKindName(m)}</span></div><div class="plan-card-bottom"><span>${icon('calendar')}${planDuration(m)}</span><a href="#plan?id=${m.id}" data-life-detail="${m.id}">${selected?icon('check')+'已选':m.status==='ready'?m.actions.length+' 个步骤': '待核实'} ${icon('arrow-up-right')}</a></div></article>`;
}
function renderDiscovery(){
 const count=lifeLibrary.modules.filter(m=>m.status==='ready').length;
 return `<div class="page discovery-page"><section class="discovery-hero"><a class="discovery-badge" href="#about">${icon('book-2')} ${count} 份可选安排，每份保留来源 ${icon('arrow-right')}</a><h1>发现适合你的<br class="mobile-break">健康生活计划</h1><p>从饮食、活动到日常习惯。选择喜欢的步骤，<br class="desktop-break">组合成自己的30天，放进手机日历。</p><div class="discovery-shortcuts"><a href="#my-plan">组合我的30天 ${icon('arrow-right')}</a><a href="#calendar">了解手机日历</a></div></section><section class="discovery-library" aria-label="浏览计划"><div class="discovery-tabs" role="group" aria-label="计划分类">${Object.entries(discoveryCategories).map(([k,[title,img]])=>`<button data-plan-category="${k}" aria-pressed="${discoverCategory===k}">${icon(img)}${title}</button>`).join('')}</div><div class="discovery-controls"><label class="discovery-search"><span class="sr-only">搜索计划、作者或目标</span>${icon('search')}<input id="life-search" type="search" placeholder="搜索计划、作者或目标…" value="${esc(lifeQuery)}" autocomplete="off"><kbd aria-hidden="true">/</kbd></label><label class="discovery-sort"><span class="sr-only">排序方式</span><select id="plan-sort"><option value="recommended"${discoverSort==='recommended'?' selected':''}>推荐顺序</option><option value="name"${discoverSort==='name'?' selected':''}>名称排序</option><option value="steps"${discoverSort==='steps'?' selected':''}>步骤由少到多</option></select></label><button class="button" id="plan-filter-toggle" aria-expanded="false" aria-controls="plan-filters">${icon('adjustments-horizontal')}筛选</button></div><div id="plan-filters" class="discovery-filters" hidden><label>内容类型<select id="life-kind">${Object.entries(lifeKinds).map(([k,v])=>`<option value="${k}"${k===lifeKind?' selected':''}>${v}</option>`).join('')}</select></label><label class="check"><input type="checkbox" id="plan-ready"${discoverReady?' checked':''}>只看可选步骤</label><label class="check"><input type="checkbox" id="plan-saved"${discoverSaved?' checked':''}>我的收藏</label><button class="reset" id="plan-reset">重置筛选</button></div><div class="discovery-results-head"><h2 id="plan-results-title">全部计划</h2><span id="plan-results-count" role="status" aria-live="polite"></span></div><div id="plan-filter-note"></div><div id="plan-results" class="plan-grid"></div><div id="plan-pagination" class="plan-pagination"></div></section><section class="discovery-bottom"><div><h2>好的计划，从看清来源开始。</h2><p>工具使用、博主学习与生活安排分别标注。<br>还没核实的内容，会保留它的缺口。</p></div><a href="#about" class="button">了解整理标准 ${icon('arrow-up-right')}</a></section><details class="reading-format source-progress"><summary>查看来源整理进度</summary><p>${lifeLibrary.counts.sources} 个已登记来源，${lifeLibrary.counts.candidate_pending} 个项目候选待审核，${lifeLibrary.counts.creator_pending} 个博主执行模块待完整口述核对。</p><button id="life-inventory" class="button">下载整理清单</button></details></div>`;
}
function renderDiscoveryResults(){
 if(!$('#plan-results'))return;
 const items=sortedPlans();$('#plan-results-title').textContent=discoverSaved?'我收藏的计划':discoverCategory==='all'?'全部计划':discoveryCategories[discoverCategory][0];$('#plan-results-count').textContent=`${items.length} 份安排`;
 $('#plan-results').innerHTML=items.length?items.slice(0,discoverLimit).map(planCard).join(''):`<div class="discovery-empty">${icon('search')}<h3>${discoverSaved?'还没有符合条件的收藏':'没有找到这样的计划'}</h3><p>试试其他关键词，或清除筛选后重新浏览。</p><button class="button" id="plan-empty-reset">查看全部计划</button></div>`;
 $('#plan-pagination').innerHTML=items.length>discoverLimit?`<button class="button" id="plan-more">查看更多 ${icon('chevron-down')}</button><span>已显示 ${Math.min(items.length,discoverLimit)} / ${items.length} 份</span>`:'';
 $('#plan-filter-note').innerHTML=lifeKind==='creator'?'<p class="notice">博主执行模块仍待口述核对，不能直接加入执行日程。可以选择单独标注的学习安排。</p>':'';
 document.querySelectorAll('[data-plan-category]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.planCategory===discoverCategory)));
 history.replaceState(null,'',discoveryHash());syncPlanBasket();
}
function syncPlanBasket(){
 let el=$('#plan-basket');if(!el){el=document.createElement('aside');el.id='plan-basket';el.setAttribute('aria-label','已选择的计划');document.body.append(el);}
 el.hidden=!lifeCart.length||!['plans','plan'].includes(page);
 const steps=lifeCart.reduce((n,s)=>n+s.actions.length,0);
 el.innerHTML=`<div>${icon('check')}<strong>已选 ${lifeCart.length} 份计划</strong><span>${steps} 个步骤，按你的节奏安排</span></div><a class="button dark" href="#my-plan">组合我的30天 ${icon('arrow-right')}</a>`;
 document.body.classList.toggle('has-plan-basket',!el.hidden);
}
function planDetailPage(id){
 const m=moduleById(id);if(!m)return `<div class="page discovery-empty"><h1>计划暂时没有找到</h1><a class="button" href="${discoveryHash()}">返回计划库</a></div>`;
 const category=planCategory(m);const related=lifeLibrary.modules.filter(x=>x.id!==id&&planCategory(x)===category&&x.status==='ready').slice(0,3);
 return `<div class="page plan-detail-page"><div class="plan-breadcrumb"><a href="${discoveryHash()}">计划库</a><span>/</span><a href="#plans?category=${category}">${discoveryCategories[category][0]}</a><span>/</span><span>${esc(planName(m))}</span></div><header class="plan-detail-header"><div class="plan-symbol symbol-${category}">${icon(discoveryCategories[category][1])}</div><div><div class="plan-detail-label">${planKindName(m)} · ${esc(m.author)}</div><h1>${esc(planName(m))}</h1><p>${esc(m.goal)}</p></div></header><div class="plan-detail-layout"><div class="plan-detail-main"><div class="plan-detail-intro"><h2>把适合的步骤，放进你的生活。</h2><p>勾选想执行的部分，再调整时间、星期和提醒。</p></div>${lifeModuleContent(m,true)}</div><aside class="plan-detail-sidebar"><h2>这份计划</h2><dl><div><dt>来源作者</dt><dd>${esc(m.author)}</dd></div><div><dt>安排周期</dt><dd>30 天 · ${planDuration(m)}</dd></div><div><dt>可选步骤</dt><dd>${m.actions.length} 个</dd></div><div><dt>当前状态</dt><dd>${m.status==='ready'?'可选择步骤':'执行内容待核实'}</dd></div></dl><button class="button" data-plan-save="${m.id}" aria-pressed="${planSaved.has(m.id)}">${icon('bookmark')}${planSaved.has(m.id)?'已收藏':'收藏计划'}</button><a class="button" href="${esc(m.sources[0].url)}" target="_blank" rel="noopener noreferrer">查看原始来源 ${icon('arrow-up-right')}</a><p>选择只是开始。以实际执行和感受为依据，随时修改自己的安排。</p></aside></div>${related.length?`<section class="plan-related"><h2>也可以看看</h2><div class="plan-grid">${related.map(planCard).join('')}</div></section>`:''}</div>`;
}
function resetDiscovery(){lifeQuery='';lifeKind='all';discoverCategory='all';discoverSort='recommended';discoverReady=true;discoverSaved=false;discoverLimit=18;renderLife();}
function applyTheme(mode){document.documentElement.dataset.theme=mode;const b=$('#theme-toggle');if(b){b.innerHTML=icon(mode==='dark'?'sun':'moon');b.setAttribute('aria-label',mode==='dark'?'切换浅色模式':'切换深色模式');}}
try{const theme=localStorage.getItem('baymax-theme');applyTheme(['dark','light'].includes(theme)?theme:matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');}catch{applyTheme('light');}
function closeNavigation(){const b=$('#nav-toggle');if(b){b.setAttribute('aria-expanded','false');$('#primary-nav').classList.remove('is-open');}}
document.addEventListener('click',e=>{
 const b=e.target.closest('button,a');if(!b)return;
 if(b.dataset.planCategory){discoverCategory=b.dataset.planCategory;discoverLimit=18;renderDiscoveryResults();}
 if(b.dataset.planSave){const id=b.dataset.planSave;planSaved.has(id)?planSaved.delete(id):planSaved.add(id);try{localStorage.setItem('baymax-plan-saved',JSON.stringify([...planSaved]));}catch{toast('当前浏览器无法保存收藏');}if(page==='plans')renderDiscoveryResults();else{b.setAttribute('aria-pressed',String(planSaved.has(id)));b.innerHTML=icon('bookmark')+(b.classList.contains('plan-bookmark')?'':planSaved.has(id)?'已收藏':'收藏计划');if(b.classList.contains('plan-bookmark'))b.setAttribute('aria-label',(planSaved.has(id)?'取消收藏 ':'收藏 ')+planName(moduleById(id)));}}
 if(b.id==='plan-filter-toggle'){const open=b.getAttribute('aria-expanded')!=='true';b.setAttribute('aria-expanded',String(open));$('#plan-filters').hidden=!open;}
 if(b.id==='plan-more'){discoverLimit+=18;renderDiscoveryResults();}
 if(['plan-reset','plan-empty-reset'].includes(b.id))resetDiscovery();
 if(b.id==='nav-toggle'){const open=b.getAttribute('aria-expanded')!=='true';b.setAttribute('aria-expanded',String(open));$('#primary-nav').classList.toggle('is-open',open);}
 if(b.id==='theme-toggle'){const mode=document.documentElement.dataset.theme==='dark'?'light':'dark';applyTheme(mode);try{localStorage.setItem('baymax-theme',mode);}catch{}}
 if(b.closest('#primary-nav')&&b.tagName==='A')closeNavigation();
});
document.addEventListener('change',e=>{
 if(e.target.id==='plan-sort')discoverSort=e.target.value;
 else if(e.target.id==='plan-ready')discoverReady=e.target.checked;
 else if(e.target.id==='plan-saved')discoverSaved=e.target.checked;
 else return;
 discoverLimit=18;renderDiscoveryResults();
});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeNavigation();if(e.key==='/'&&!e.ctrlKey&&!e.metaKey&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)&&!$('#modal').open&&$('#life-search')){e.preventDefault();$('#life-search').focus();}});
