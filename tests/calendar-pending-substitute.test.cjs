'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(process.argv[2] ?? require('node:path').join(__dirname,'../index.html'),'utf8');
const src=html.split('<script>')[1].split('</script>')[0];
const makeNode=()=>({value:'',html:'',options:[],style:{},classList:{add(){},remove(){}},addEventListener(){},appendChild(o){this.options.push(o);},querySelector(){return null;},set innerHTML(v){this.html=v;this.options=Array.from(v.matchAll(/<option value=/g));},get innerHTML(){return this.html;}});
const nodes=new Map(),get=id=>nodes.get(id)??(nodes.set(id,makeNode()),nodes.get(id));
const context={document:{createElement:()=>makeNode(),getElementById:get,addEventListener(){},querySelectorAll:()=>[],querySelector:()=>null,body:{appendChild(o){nodes.set(o.id,o);}}},window:{addEventListener(){}},localStorage:{getItem:()=>null},console,TextEncoder,TextDecoder,Blob,setTimeout,clearTimeout,setInterval,clearInterval,Intl,location:{origin:'http://127.0.0.1'}};
vm.createContext(context);
vm.runInContext(src.slice(0,src.indexOf('function bootUI()')),context);
const t=(q)=>JSON.parse(vm.runInContext('JSON.stringify('+q+')',context));
assert.ok(html.indexOf('data-v="calendar"')<html.indexOf('data-v="att"'));
assert.match(html,/id="v-calendar"/);
const run=s=>vm.runInContext(s,context);
get('pYear').value='2027';get('pMonth').value='1';
run(`
const e={id:'fixture',name:'合成員工',payType:'monthly',base:36000,hire:'2024-01-01',sched:defaultSched()};
state.employees=[e];localDB.ready=true;activeView=()=> 'calendar';save=()=>{};renderActive=()=>{};renderDet=()=>{};
let notices=[];toast=s=>{notices.push(s);};
let output=[];dl=(blob,name)=>output.push({blob,name});window.print=()=>output.push({name:'print'});
for(let i=1;i<6;i++)Object.assign(e.sched['d'+i],{start:'09:00',end:'17:00'});
const p=calendarDefaultDraft(e), desired={'02-06':'01-04','02-07':'02-10','02-28':'03-01','04-04':'04-06','05-01':'04-30','10-10':'10-11','12-25':'12-24'};
p.rows.filter(x=>x.mode==='substitute').forEach(x=>{
  x.target='2027-'+desired[x.source.slice(5)];x.note='合成測試核對';x.consent=true;
});
p.coverage='lsa';p.regularSchedule=true;
Object.assign(p.rows.find(x=>x.source==='2027-12-25'),{target:'',note:'',consent:false});
const fillMonth=ym=>{
 const rec=mrec(e.id,ym), R=ymRange(ym), hs=employeeHolidaySet(e);
 for(let t=R.start;t<R.end;t+=DAY){const date=fd(t); if(calType(e,date)==='work'&&calEmployed(e,date)){
   rec.days.push({date,wk:wkOf(date),status:hs.has(date)?'holiday':'work',kind:'work',hours:8});
 }}
 return rec;
};
const dec='2027-12';
const month='2027-01';
`);
const formRows=(plan)=>{
 get('calCoverage').checked=true;get('calBasis').value=plan.basis;
 plan.rows.forEach((x,i)=>{
  get('calMode'+i).value=x.mode;get('calTarget'+i).value=x.target;
  get('calNote'+i).value=x.note;get('calConsent'+i).checked=x.consent;
 });
};
const propose=(source,edits)=>t(`(()=>{const p1=JSON.parse(JSON.stringify(calendarPlan(e)||p));Object.assign(p1.rows.find(x=>x.source===${JSON.stringify(source)}),${JSON.stringify(edits)});return p1})()`);
function savePlan(ym,plan){
 get('pMonth').value=String(Number(ym.slice(5)));
 run('openCalendar(e.id,'+JSON.stringify(ym)+',false)');
 formRows(plan);
 run('saveCalendarDialog()');
 return t('notices.at(-1)');
}
const decSource='2027-12-25';
assert.match(savePlan('2027-01',t('p')),/已儲存/,'first annual save allows unresolved December');
assert.deepEqual(t('calendarPlanIssues(e,calendarPlan(e),month)'),[]);
run('const jr=fillMonth(month), dr=fillMonth(dec);');
run('openCalendar(e.id,month,false)');
formRows(t('calendarPlan(e)'));
get('calReviewer').value='合成核對者';get('calMonthNote').value='合成核對';get('calSpecial').checked=true;get('calRegular').checked=true;
run('confirmCalendarDialog()');
assert.equal(t('jr.calendarReview.verified'),true,'Jan modal monthly review really saves');
run('verifiedLeaveClose(curYM(),{pending:0,needsProof:0,approved:0,unknown:0},Date.now())');
assert.equal(t('setConfirm(e.id,true)'),true,'Jan actual payroll confirmation');
const frozen=t('({jr,w:compute(e,month),label:employeeHolidayName(e,"2027-01-01")})');
assert.equal(frozen.w.net,36000);
assert.match(t('calendarMonthIssues(e,dec,dr,true).join(";")'),/2027-12-25 待約定補假日/);
get('pMonth').value='12';
assert.equal(t('setConfirm(e.id,true)'),false);
assert.throws(()=>run("recordCalendarReview(e,dec,dr,'合成核對','測試者','noneThisMonth',false)"),/待約定補假日/);
assert.match(t('employeeHolidayName(e,"2027-12-25")'),/當月假日待核/);
for(const [src,edit,reason] of [
 [decSource,{consent:true},/依據/],
 [decSource,{note:'自稱已同意'},/目標日期無效/],
 [decSource,{mode:'transfer'},/依據/],
 [decSource,{target:'2027-12-32',note:'合成核對'},/目標日期無效/],
 [decSource,{target:'2028-01-03',note:'合成核對'},/目標日期無效/],
 [decSource,{target:'2027-10-11',note:'合成核對'},/重疊/],
 ['2027-06-09',{mode:'substitute',target:'',note:'',consent:false},/依據/],
 [decSource,{target:'2027-01-06',note:'合成核對'},/2027-01 已確認薪資/]
]){
 assert.match(savePlan('2027-12',propose(src,edit)),reason);
 assert.equal(t('calendarPlan(e).revision'),1);
}
run("state.settings.holidays='2027-12-22 額外測試假日'");
assert.match(savePlan('2027-12',t('calendarPlan(e)')),/額外全域假日/);
run("state.settings.holidays='';e.leave='2027-12-20';");
assert.match(savePlan('2027-12',t('calendarPlan(e)')),/不在任職期間|依據/);
run("delete e.leave");
const valid=propose(decSource,{target:'2027-11-30',note:'合成約定，兩月皆未確認'});
assert.match(savePlan('2027-12',valid),/已儲存/);
assert.equal(t('calendarPlan(e).revision'),2);
assert.deepEqual(t('calendarMonthIssues(e,dec,dr,true)'),[],'resolved source month can be reviewed');
assert.equal(t('employeeHolidaySet(e,"2027-11").has("2027-11-30")'),true,'known cross-month target is classified');
assert.deepEqual(t('({jr,w:compute(e,month),label:employeeHolidayName(e,"2027-01-01")})'),frozen);
console.log('PASS pending December first annual save, actual January review and confirmation, December fail-closed until resolved, rejected invalid/colliding/closed target and unsupported global settings, open cross-month resolution, frozen January');
