'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../index.html'),'utf8').split('<script>')[1].split('</script>')[0];
assert(source.includes('function bootUI()'));
const date='2026-11-16', year='2026', month='11';
const els=new Map(),node=()=>({value:'',options:[],appendChild(x){this.options.push(x);},addEventListener(){},style:{}});
const get=id=>els.get(id)??(els.set(id,node()),els.get(id));
const ctx=vm.createContext({document:{getElementById:get,createElement:node,addEventListener(){},querySelectorAll:()=>[]},window:{addEventListener(){}},Intl,console,setTimeout,clearTimeout});
const r=s=>vm.runInContext(s,ctx),read=s=>JSON.parse(r('JSON.stringify('+s+')'));
r(source.slice(0,source.indexOf('function bootUI()')));
get('pYear').value=year;get('pMonth').value=month;
r(`
const ym="2026-11",day="2026-11-16", first='A'.repeat(20),other='B'.repeat(20);
const claim=(type,extra={})=>({employeeId:'calc-fixture-id',date:day,type,minutes:0,start:'',end:'',status:'approved',scope:'production',...extra});
let nWrites=0;
function setup({hourly=false,workday=8}={}){
 const e={id:'calc-fixture-id',name:'測試員工',payType:hourly?'hourly':'monthly',base:36000,rate:220,perfect:1000,summer:0,otFixed:0,labor:0,health:0,fixedItems:[],hire:'2024-01-01',leaveSystem:'cal',yearEnd:'carry',brkMin:30,brkAfter:4,sched:defaultSched()};
 const g={type:'work',start:'13:30',end:workday===8?'22:00':'20:30',breakM:30};
 for(let i=1;i<=5;i++)e.sched['d'+i]={...g};
 state={version:3,settings:DEF_SETTINGS(),employees:[e],months:{}};
 localDB.ready=true;sec.key={};sec.locked=false;sec.locking=false;cloud.conflict=false;nWrites=0;
 return e;
}
dataOp=fn=>Promise.resolve().then(()=>fn(dataEpoch));
replaceLocalState=async (next,k,s,e,expected)=>{validateState(next);if(JSON.stringify(state)!==expected)throw Error('測試狀態已更新');state=JSON.parse(JSON.stringify(next));nWrites++};
savedOK=schedulePush=renderActive=toast=save=renderSlips=()=>{};
const raw=()=>leaveDeskRaw('calc-fixture-id',ym);
const calc=()=>computeLive(emp('calc-fixture-id'),ym,raw()||blankRec());
const amounts=()=>{const c=calc();return {net:c.net,gross:c.gross,attendance:c.earnings.find(x=>x[0]==='全勤獎金')?.[1]||0,unpaid:c.deducts.find(x=>x[0]==='事假扣薪')?.[1]||0,sick:c.deducts.find(x=>x[0]==='病假扣薪')?.[1]||0,annual:c.leave.annualH,hours:raw()?.days[0]?.hours??null,pending:c.reviews.filter(x=>x.st==='pending').map(x=>x.key)};};
`);
(async()=>{
 const table=[];
 const cases=[
  ['annual',0,0,8,1000],['paidLeave',0,0,0,1000],['personal',1200,0,0,0],
  ['family',1233,0,0,1000],['carePersonal',1233,0,0,1000],['sick',0,616,0,967]
 ];
 const approve=()=>r("approveAll('calc-fixture-id')");
 r('setup()');
 const base=read('amounts()');
 for(const [type,unpaid,sick,annual,attendance] of cases){
  r('setup()');
  const status=await r(`leavePortalApply(claim('${type}',{status:'pending'}),first)`);
  assert.equal(status.ok,false);
  assert.equal(read('nWrites'),0);
  const z=await r(`leavePortalApply(claim('${type}'),first)`);assert.equal(z.ok,true,JSON.stringify(z));
  approve();
  const a=read('amounts()');table.push({type,...a,delta:a.net-base.net});
  assert.equal(a.annual,annual,type);assert.equal(a.attendance,attendance,type);assert.equal(a.hours,8,type);
  assert.equal(a.unpaid,unpaid,type);assert.equal(a.sick,sick,type);
  const re=await r(`leavePortalApply(claim('${type}'),first)`);assert.equal(re.already,true);
  assert.equal((await r(`leavePortalApply(claim('${type}'),other)`)).ok,false);
  assert.equal(read('nWrites'),1);assert.deepEqual(read('amounts()'),a);
 }
 console.table(table);
 r('setup({workday:6.5})');
 assert.equal((await r("leavePortalApply(claim('annual'),first)")).ok,true);
 assert.equal(read('amounts().annual'),6.5);
 r('setup()');
 const p=await r("leavePortalApply(claim('personal',{start:'13:30',end:'17:30',minutes:240}),first)");
 assert.equal(p.ok,false); assert.match(p.error,/部分時段/);assert.equal(read('nWrites'),0);
 const manual=await r("leaveDeskRegister({id:'calc-fixture-id',date:day,type:'personal',full:false,hours:4},leaveDeskInspect('calc-fixture-id',day).token)");
 assert.equal(manual.ok,true);approve();const four=read('amounts()');assert.equal(four.hours,4);assert.equal(four.unpaid,600);
 r('setup()');
 const realBreak=await r("leaveDeskRegister({id:'calc-fixture-id',date:day,type:'personal',full:false,hours:3.5},leaveDeskInspect('calc-fixture-id',day).token)");
 assert.equal(realBreak.ok,true);approve();const threeHalf=read('amounts()');assert.equal(threeHalf.hours,3.5);assert.equal(threeHalf.unpaid,525);
 r('setup()');
 assert.equal((await r("leavePortalApply(claim('annual'),first)")).ok,true);
 assert.equal((await r("leavePortalApply(claim('annual',{date:'2026-11-17'}),other)")).ok,true);
 assert.equal(read('amounts().annual'),16);
 assert.equal((await r("leavePortalApply(claim('annual',{date:'2026-12-01'}),'C'.repeat(20))")).ok,false);
 assert.equal(read('nWrites'),2);
 r('setup({hourly:true})');
 assert.equal((await r("leavePortalApply(claim('annual'),first)")).ok,false);
 assert.equal(read('nWrites'),0);
 r('setup();state.months[ym]={"calc-fixture-id":blankRec()};raw().days=[{date:day,status:"work",kind:"work",in:"13:30",out:"22:00",hours:8,wh:480,punches:2}]');
 assert.equal((await r("leavePortalApply(claim('personal'),first)")).ok,false);assert.equal(read('nWrites'),0);
 r('setup();state.months[ym]={"calc-fixture-id":blankRec()};raw().confirmed=true');
 assert.equal((await r("leavePortalApply(claim('annual'),first)")).ok,false);assert.equal(read('nWrites'),0);
 console.log('BASE',base,'MANUAL_4H',four,'MANUAL_3H30',threeHalf);
 console.log('PASS full pipeline leavePortalApply -> validated payroll attendance -> computeLive; part-time / partial / duplicates / locked months stay safe.');
})().catch(e=>{console.error(e);process.exitCode=1;});
