'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(process.argv[2] || 'index.html','utf8');
const src=html.split('<script>')[1].split('</script>')[0];
const makeNode=()=>({value:'',html:'',options:[],style:{},classList:{add(){},remove(){}},addEventListener(){},appendChild(o){this.options.push(o);},querySelector(){return null;},set innerHTML(v){this.html=v;this.options=Array.from(v.matchAll(/<option value=/g));},get innerHTML(){return this.html;}});
const nodes=new Map(),get=id=>nodes.get(id)??(nodes.set(id,makeNode()),nodes.get(id));
const context={document:{createElement:()=>makeNode(),getElementById:get,addEventListener(){},querySelectorAll:()=>[],querySelector:()=>null,body:{appendChild(o){nodes.set(o.id,o);}}},window:{addEventListener(){}},localStorage:{getItem:()=>null},console,TextEncoder,TextDecoder,setTimeout,clearTimeout,setInterval,clearInterval,Intl,location:{origin:'http://127.0.0.1'}};
vm.createContext(context);
vm.runInContext(src.slice(0,src.indexOf('function bootUI()')),context);
const t=(q)=>JSON.parse(vm.runInContext('JSON.stringify('+q+')',context));

get('pYear').value='2027';get('pMonth').value='1';
vm.runInContext(`
  const fixture={id:'fixture',name:'測試老師',payType:'monthly',hire:'2024-01-01',sched:defaultSched(),base:36000,brkMin:30,brkAfter:4};
  state.employees=[fixture];localDB.ready=true;
  const candidate=calendarDefaultDraft(fixture);
  const targets={'02-06':'02-09','02-07':'02-10','02-28':'03-01','04-04':'04-06','05-01':'04-30','10-10':'10-11','12-25':'12-24'};
  candidate.rows.filter(x=>x.mode==='substitute').forEach(x=>{x.target='2027-'+targets[x.source.slice(5)];x.note='測試約定日期';});
  candidate.coverage='lsa';candidate.regularSchedule=true;recordCalendarPlan(fixture,candidate);
  det.id='fixture';save=()=>{};renderDet=()=>{};renderAtt=()=>{};openAbs=()=>{};toast=()=>{};addLog=()=>{};
  const setup=(end,month)=>{
    state.months={};
    for(let i=1;i<=5;i++)Object.assign(fixture.sched['d'+i],{start:'13:30',end});
    genDays();
    const m=mrec(fixture.id),h=m.days.find(x=>x.status==='holiday');
    const punchRows=[['中文姓名','日期','星期','打卡','備註']];
    for(const [i,d] of m.days.entries()){
      const isHoliday=d.status==='holiday';
      punchRows.push([i===0?fixture.name:'',d.date,d.wk,isHoliday?'':'13:30',isHoliday?'':'WH=8H00']);
      if(!isHoliday)punchRows.push(['','','',end,'']);
      if(d.status==='pending')Object.assign(d,{status:'work',hours:scheduledPaidHours(fixture,d.wk,d.date)});
    }
    return {m,h,punchRows};
  };
`,context);
for(const [end,hours] of [['20:30',6.5],['21:30',7.5],['22:00',8]]){
  // Exercise both real generation and real parsed attendance-row ingest.
  const q=`setup('${end}')`;
  vm.runInContext(`var fx=${q};renderDay();`,context);
  assert.equal(t('fx.h.hours'),null);
  assert.equal(t('dayAgg(fixture,fx.m).holidayH'),hours);
  assert.match(get('detWrap').innerHTML,new RegExp('01-01[^]*?placeholder="'+hours+'"'));
  assert.match(get('detSummary').innerHTML,new RegExp('國定假日 '+hours+'h'));
  assert.deepEqual(t("calendarMonthIssues(fixture,'2027-01',fx.m,true)"),[]);
  assert.equal(t("scheduledPaidHours(fixture,fx.m.days[0].wk,fx.m.days[0].date)"),hours);
  assert.equal(t("(recordCalendarReview(fixture,'2027-01',fx.m,'查核','測試','noneThisMonth',false),calendarMonthIssues(fixture,'2027-01',fx.m).length)"),0);
  vm.runInContext("ingestRows(fx.punchRows,'synthetic.csv');renderDay();",context);
  assert.match(get('parseMsg').innerHTML,/打卡匯入成功/);
  assert.deepEqual(t("[fx.m.days[0].status,fx.m.days[0].hours,dayAgg(fixture,fx.m).holidayH]"),['holiday',null,hours]);
  assert.deepEqual(t("calendarMonthIssues(fixture,'2027-01',fx.m,true)"),[]);
  assert.equal(t("scheduledPaidHours(fixture,fx.m.days[0].wk,fx.m.days[0].date)"),hours);
  assert.equal(t("(recordCalendarReview(fixture,'2027-01',fx.m,'查核','測試','noneThisMonth',false),(fx.m.reviews.workMinutes={v:computeLive(fixture,curYM(),fx.m).reviews.find(x=>x.key==='workMinutes').sig,d:'ok'}),setConfirm(fixture.id,true))"),true);
  vm.runInContext("var snap=JSON.stringify(fx.m.snapshot);ingestRows(fx.punchRows,'synthetic.csv')",context);
  assert.match(get('parseMsg').innerHTML,/已確認未覆蓋/);
  assert.equal(t('JSON.stringify(fx.m.snapshot)===snap'),true);
  assert.equal(t("dayAgg(fixture,fx.m).holidayH"),hours);
  vm.runInContext("renderDay()",context);
  assert.match(get("detWrap").innerHTML,new RegExp("01-01[^]*?placeholder=\""+hours+"\" disabled"));
}
vm.runInContext("fx=setup('20:30');fx.h.hours=0",context);
assert.equal(t('dayAgg(fixture,fx.m).holidayH'),0);
assert.deepEqual(t("calendarMonthIssues(fixture,'2027-01',fx.m,true)"),[]);
vm.runInContext('fx.h.hours=6.25;renderDay()',context);
assert.equal(t('dayAgg(fixture,fx.m).holidayH'),6.25);
assert.match(get('detWrap').innerHTML,/01-01[^]*?value="6.25" placeholder="6.5"/);
vm.runInContext('fx.h.hours=8',context);
assert.equal(t('dayAgg(fixture,fx.m).holidayH'),8);
assert.match(t("calendarMonthIssues(fixture,'2027-01',fx.m,true).join(';')"),/2027-01-01 假別／照給時數/);
vm.runInContext("fx.h.hours=null;fixture.payType='hourly';state.settings.hourlyHolidayOff=true",context);
assert.equal(t('dayAgg(fixture,fx.m).holidayH'),0);
vm.runInContext('state.settings.hourlyHolidayOff=false',context);
assert.equal(t('dayAgg(fixture,fx.m).holidayH'),6.5);
vm.runInContext("fixture.payType='monthly';fx.m.snapshot={net:12345,late:{totalMin:0}};fx.m.confirmed=true;var frozen=JSON.stringify(fx.m);renderDay()",context);
assert.equal(t('compute(fixture).net'),12345);
assert.equal(t('JSON.stringify(fx.m)===frozen'),true);
assert.match(get('detWrap').innerHTML,/01-01[^]*?placeholder="8" disabled/);
assert.equal(t('dayAgg(fixture,fx.m).holidayH'),8);
assert.equal(t("dayAgg(fixture,{...blankRec(),days:[{date:'2026-01-01',wk:'四',status:'holiday',hours:null}]}).holidayH"),8);
assert.equal(t("dayAgg(fixture,{...blankRec(),days:[{date:'2027-01-04',wk:'一',status:'holiday',hours:null}]}).holidayH"),8);
console.log('Mapped holiday QA passed: 6.5/7.5/8 generated and imported, UI/review consistency, explicit override, hourly-off, frozen and legacy.');
