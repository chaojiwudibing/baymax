// Run with node community/tests/check_frontend.cjs. No installed packages required.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const elements=new Map();
const element=()=>({innerHTML:'',textContent:'',hidden:false,open:false,addEventListener(){},close(){},setAttribute(){},classList:{add(){},remove(){},toggle(){}}});
const storage=new Map([['bodycommons-compare','["missing","missing",123]']]);
const context=vm.createContext({Intl,URLSearchParams,setTimeout:()=>0,clearTimeout(){},fetch:()=>new Promise(()=>{}),localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},location:{hash:'#directory'},history:{replaceState(){}},window:{addEventListener(){},scrollTo(){}},document:{addEventListener(){},querySelector(q){if(!elements.has(q))elements.set(q,element());return elements.get(q);},querySelectorAll:()=>[],createElement:element,body:{append(){},classList:{toggle(){}}}}});
for(const file of ['features.js','app.js'])vm.runInContext(fs.readFileSync(path.join(root,'public',file),'utf8'),context);
context.fixture=JSON.parse(fs.readFileSync(path.join(root,'data/catalog.json')));
context.creatorsFixture=JSON.parse(fs.readFileSync(path.join(root,'data/creators.json')));
vm.runInContext('catalog=fixture;creatorLibrary=creatorsFixture;community={posts:[],comments:[],submissions:[],videos:[]};',context);
const run=code=>vm.runInContext(code,context);
assert.equal(run('filtered().length'),context.fixture.curatedCount);
run("state.category='food';state.license='AGPL-3.0';state.selfHosted=true;state.activeOnly=true;");
const matches=run('filtered()');assert.ok(matches.length>0);assert.ok(matches.every(r=>r.category==='food'&&r.license==='AGPL-3.0'&&!r.archived&&r.tags.includes('自托管')));
run("Object.assign(state,{category:'all',license:'all',selfHosted:false,activeOnly:false,language:'Python'});");
assert.ok(run('filtered()').every(r=>r.language==='Python'));
run('syncCompare()');assert.equal(run('comparing.length'),0);
run("catalog.resources.filter(r=>r.curated).slice(0,5).forEach(r=>toggleCompare(r.id));");assert.equal(run('comparing.length'),4);
assert.equal(JSON.parse(storage.get('bodycommons-compare')).length,4);
run('toggleCompare(comparing[0])');assert.equal(run('comparing.length'),3);
const similar=run("similarResources(resource('mealie-recipes/mealie'))");assert.ok(similar.length>0);assert.ok(similar.every(r=>r.curated&&r.category==='food'&&r.kind==='应用'&&r.id!=='mealie-recipes/mealie'));
for(let i=0;i<6;i++){assert.ok(run(`collections[${i}].ids.every(id=>resource(id))`),'Topic resource missing: '+i);const html=run(`renderTopic(${i})`);assert.ok(html.includes('原项目与安装说明'));assert.ok(!html.includes('undefined'));}
run("community.posts=[{id:1,project:'mealie-recipes/mealie',author:'真实测试',title:'采购清单导出',body:'使用经历',kind:'使用体验',created:'2026-10-07',replies:0},{id:2,project:'wger-project/wger',author:'另一位',title:'日志记录',body:'使用经历',kind:'求助',created:'2026-10-07',replies:0}];state.postProject='mealie-recipes/mealie';state.postQuery='采购';");
const posts=run('postRows()');assert.ok(posts.includes('采购清单导出'));assert.ok(!posts.includes('日志记录'));
(async()=>{
  // A slower old project request must not overwrite the user's newer project route.
  const pending=[];context.nextRequest=()=>new Promise(resolve=>pending.push(resolve));run('api=nextRequest;');
  context.location.hash='#community?project=mealie-recipes%2Fmealie';const first=run('navigate()');
  context.location.hash='#community?project=wger-project%2Fwger';const second=run('navigate()');
  const empty={posts:[],comments:[],submissions:[],videos:[]};pending[1](empty);await second;pending[0](empty);await first;
  assert.equal(run('state.postProject'),'wger-project/wger');
  console.log('Frontend checks passed: filters, shortlist limits, related resources, topic links, discussion filtering, navigation race.');
})().catch(err=>{console.error(err);process.exitCode=1;});
