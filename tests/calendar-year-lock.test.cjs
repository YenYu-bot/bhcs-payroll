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
recordCalendarPlan(e,p);
const fillMonth=ym=>{
 const rec=mrec(e.id,ym), R=ymRange(ym), hs=employeeHolidaySet(e);
 for(let t=R.start;t<R.end;t+=DAY){const date=fd(t); if(calType(e,date)==='work'&&calEmployed(e,date)){
   rec.days.push({date,wk:wkOf(date),status:hs.has(date)?'holiday':'work',kind:'work',hours:8});
 }}
 return rec;
};
const jr=fillMonth('2027-01');
recordCalendarReview(e,'2027-01',jr,'合成出勤一致','合成核對者','noneThisMonth',false);
// Simulate an existing whole-year review created before this patch; do not rewrite it on load/save.
jr.calendarReview.sig=JSON.stringify({source:calendarSourceSig(e),ym:'2027-01',...calendarMonthEvidence(jr)});
`);
assert.deepEqual(t('((r)=>[r.settlementBlocked,r.leavePayrollBlocks,r.pendingReviews])(computeLive(e,"2027-01",jr))'),[false,[],0]);
assert.equal(t('setConfirm(e.id,true)'),true);
const baseline = t('({annual:calendarPlan(e),january:jr,confirmedView:compute(e,"2027-01")})');
assert.equal(baseline.january.confirmed,true);
assert.equal(baseline.confirmedView.locked,true);
assert.equal(baseline.confirmedView.net,36000);
const freezeOutputs=async()=>{
 get('pMonth').value='1';
 run('output=[];exportExcel();exportWord();printPayroll()');
 const files=run('output');
 assert.equal(files.length,3);
 return Promise.all(files.map(async({name,blob})=>({name,bytes:blob?Buffer.from(await blob.arrayBuffer()).toString('base64'):null})));
};
const initialOutputs=freezeOutputs();
const takeState=()=>t('({annual:calendarPlan(e),january:jr,confirmedView:compute(e,"2027-01")})');
assert.equal(t("(openCalendar(e.id,'2027-01',false),calendarDialog)"),null);
get('pMonth').value='6';
run(`
const june='2027-06';
const ju=fillMonth(june);
recordCalendarReview(e,june,ju,'合成六月出勤一致','合成核對者','noneThisMonth',false);
const transfer=JSON.parse(JSON.stringify(p));
Object.assign(transfer.rows.find(x=>x.source==='2027-06-09'),
 {mode:'transfer',target:'2027-06-10',note:'合成書面約定',consent:true});
`);
assert.deepEqual(t('calendarPlanIssues(e,transfer)'),[],'staff/date/schedule/consent make future-only transfer valid absent the year lock');
assert.deepEqual(t('calendarMonthIssues(e,june,ju,true)'),[],'control: before departure June is otherwise valid');
run("openCalendar(e.id,'2027-06',false)");

const formRows=(plan)=>{
 get('calCoverage').checked=true;get('calBasis').value=plan.basis;
 plan.rows.forEach((x,i)=>{
  get('calMode'+i).value=x.mode;get('calTarget'+i).value=x.target;
  get('calNote'+i).value=x.note;get('calConsent'+i).checked=x.consent;
 });
};
assert.match(get('calendarModal').innerHTML,/id="calTarget\d+" value="2027-01-01" disabled/);
assert.match(get('calendarModal').innerHTML,/id="calTarget\d+" value="2027-01-04" disabled/);
assert.match(get('calendarModal').innerHTML,/id="calTarget\d+" value="2027-06-09">/);
formRows(t('transfer'));
run('saveCalendarDialog()');
assert.equal(t('calendarPlan(e).revision'),2);
assert.match(t('notices.at(-1)'),/已儲存/);
assert.deepEqual(takeState().january,baseline.january,'frozen January bytes including review');
assert.deepEqual(takeState().confirmedView,baseline.confirmedView,'frozen January payroll result');
assert.deepEqual(t('["2027-01-01","2027-01-04","2027-06-09","2027-06-10"].map(d=>employeeHolidaySet(e).has(d))'),[true,true,false,true]);
assert.equal(t('calendarReviewMatches(e,"2027-01",jr)'),true,'same closed-month review still matches');
assert.equal(t('calendarReviewMatches(e,june,ju)'),false,'only affected June review is invalid');
assert.match(t('calendarMonthIssues(e,june,ju,true).join(";")'),/2027-06-09 並非映射後的國定日/);
assert.match(t('calendarMonthIssues(e,june,ju,true).join(";")'),/2027-06-10 假日出勤類型不一致/);
assert.equal(t('setConfirm(e.id,true)'),false,'unchanged stale attendance must block regardless of approval');

const changeRow=(source,edits)=>t(`(()=>{const next=JSON.parse(JSON.stringify(calendarPlan(e)));Object.assign(next.rows.find(x=>x.source===${JSON.stringify(source)}),${JSON.stringify(edits)});return next})()`);
const assertClosedDenied=plan=>{
 const frozen=takeState();
 run("openCalendar(e.id,'2027-06',false)");
 formRows(plan);
 run('saveCalendarDialog()');
 assert.match(t('notices.at(-1)'),/2027-01 已確認薪資/);
 assert.deepEqual(takeState(),frozen);
};
assertClosedDenied(changeRow('2027-06-09',{target:'2027-01-06'})); // enter a closed month
assertClosedDenied(changeRow('2027-02-06',{target:'2027-02-09'})); // leave a closed month
assertClosedDenied(changeRow('2027-01-01',{mode:'transfer', target:'2027-06-14', consent:true, note:'合成跨月'})); // old source is closed
assertClosedDenied(changeRow('2027-01-01',{note:'另一依據'})); // end date equal, source metadata changed
const policies=t('calendarPlan(e)');policies.basis='另一年度依據';assertClosedDenied(policies);

run("closeCalendarDialog();e.leave='2027-06-15';");
assert.match(t('calendarPlanIssues(e).join(";")'),/2027-09-15 不在任職期間/);
assert.match(t('calendarMonthIssues(e,june,ju,true).join(";")'),/2027-06-16 出勤超出任職期間/);
assert.doesNotMatch(t('calendarMonthIssues(e,june,ju,true).join(";")'),/2027-09-15/);
assert.match(t('calendarMonthIssues(e,"2027-09",blankRec(),true).join(";")'),/2027-09-15 不在任職期間/);
assert.equal(t('employeeHolidaySet(e).has("2027-01-01")'),true,'June departure cannot remove earlier live holiday');
assert.match(t('employeeHolidayName(e,"2027-01-01")'),/元旦|開國/);
assert.equal(t('setConfirm(e.id,true)'),false,'future-stale leave/attendance is not silently approved');
run('output=[];exportExcel();exportWord();printPayroll()');
assert.equal(t('output.length'),0,'no actual document download or print accepted while June is blocked');
assert.deepEqual(takeState().january,baseline.january);
assert.deepEqual(takeState().confirmedView,baseline.confirmedView);
run(`
const corrected=JSON.parse(JSON.stringify(calendarPlan(e)));
for(const row of corrected.rows)if(row.source>'2027-06-15')Object.assign(row,{mode:'outside',target:'',note:'已核對離職日',consent:false});
recordCalendarPlan(e,corrected);
`);
assert.deepEqual(t('calendarPlanIssues(e)'),[]);
assert.equal(t('setConfirm(e.id,true)'),false,'post-departure attendance still independent blocker');
run(`
ju.days=ju.days.filter(d=>d.date<='2027-06-15');
Object.assign(ju.days.find(x=>x.date==='2027-06-09'),{status:'work'});
Object.assign(ju.days.find(x=>x.date==='2027-06-10'),{status:'holiday'});
recordCalendarReview(e,june,ju,'合成出勤修正','合成核對者','noneThisMonth',false);
`);
assert.deepEqual(t('calendarMonthIssues(e,june,ju)'),[]);
assert.deepEqual(takeState().january,baseline.january);
assert.deepEqual(takeState().confirmedView,baseline.confirmedView);

run("openCalendar(e.id,'2027-06',false)");
const modalEdit=t('calendarPlan(e)');
run(`const later=JSON.parse(JSON.stringify(calendarPlan(e)));
later.rows.find(x=>x.source==='2027-06-09').note='另一合成同意';
recordCalendarPlan(e,later);`);
formRows(modalEdit);
run('saveCalendarDialog()');
assert.match(t('notices.at(-1)'),/已變更|請重新開啟/,'stale modal must fail without overwriting newer evidence');
assert.equal(t("calendarPlan(e).rows.find(x=>x.source==='2027-06-09').note"),'另一合成同意');

Promise.all([initialOutputs,freezeOutputs()]).then(([original,latest])=>{
 assert.deepEqual(latest,original,'Workbooks and Word output remain byte-identical; print remains allowed for confirmed January');
 console.log("PASS real January confirmation, legacy review, byte-identical Excel/Word, June-only change, closed source and old/new target guards, separate departure/attendance blocks, and stale modal");
}).catch(e=>{console.error(e);process.exitCode=1;});
