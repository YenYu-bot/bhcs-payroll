'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../index.html'),'utf8').split('<script>')[1].split('</script>')[0];
const blank={style:{},addEventListener(){},appendChild(){},classList:{add(){},remove(){}}};
const inputs={pYear:{value:'2026'},pMonth:{...blank,value:'11'},parseMsg:{innerHTML:''}};
const context=vm.createContext({document:{createElement:()=>({}),getElementById:k=>inputs[k]??blank,addEventListener(){},querySelectorAll:()=>[]},window:{addEventListener(){}},Intl,console,setTimeout,clearTimeout});
const run=s=>vm.runInContext(s,context);
const read=s=>JSON.parse(run('JSON.stringify('+s+')'));
run(source.slice(0,source.indexOf('function bootUI()')));
inputs.pMonth.value='11';inputs.pYear.value='2026';
run(`
const ym='2026-11',sat='2026-11-07',mon='2026-11-09';
localDB.ready=true;
save=renderSlips=renderAtt=toast=()=>{};
function fixture({work=true,academic=false,noBalance=false}={}){
  state={version:3,settings:DEF_SETTINGS(),employees:[],months:{}};
  const e={id:'SYN',empNo:'SYN-01',name:'合成休息日員工',payType:'monthly',base:36000,hourBasis:'punch',hire:'2024-01-01',sched:defaultSched(),fixedItems:[],leaveSystem:'anniv',yearEnd:'pay'};
  if(noBalance){e.hire='2026-07-01';}
  e.sched.d6={type:'rest',start:'09:00',end:'12:00'};
  e.sched.d1={type:'work',start:'09:00',end:'18:00'};
  state.employees.push(e);
  if(work){
    const headers=['員工編號','中文姓名','日期','打卡','備註'];
    ingestRows([headers,[e.empNo,e.name,sat,'09:00',''],['','',sat,'10:00','WH=01H00']],'synthetic.xlsx');
    if(!commitAttendanceImport())throw Error('synthetic punch import failed');
  }
  const r=mrec(e.id,ym);
  if(academic)r.schoolPay={ym,mode:'academic',start:'',end:'',allowance:4000,attendance:0,cut:0,basis:'合成測試',fridays:[],bonus:null};
  return {e,r};
}
const amount=(rows,name)=>rows.find(x=>x[0]===name)?.[1];
const values=c=>[c.ot.rest,amount(c.earnings,'加班費'),c.annualLeft,amount(c.deducts,'事假扣薪')];
const live=o=>computeLive(o.e,ym,o.r);
const partial=fixture();partial.r.annualEvents=[{date:sat,hours:2}];let c=live(partial);
`);
assert.deepEqual(read('values(c)'),[1,200,10,0]);
assert.deepEqual(read('restAnnualQuote(150,180,60,120)'),{workedMin:60,annualMin:120,workedPay:200,annualPay:450,total:650});
run('setReview(partial.e.id,"ot","ok");c=live(partial)');
assert.equal(run('c.pendingReviews'),0);
assert.equal(run('c.settlementBlocked'),true);
assert.match(run('c.leavePayrollBlocks[0]'),/休息日約定出勤涉及請假/);
assert.equal(run('setConfirm(partial.e.id,true)'),false);
assert.equal(run('payrollReadyForOutput(false)'),false);
assert.equal(run('partial.r.annualEvents[0].hours'),2,'preserve source record');
assert.equal(run('leaveStatus(partial.e,Date.UTC(2026,11,1)).cur.remaining'),10);
assert.equal(run('leaveStatus(partial.e,Date.UTC(2026,11,31)).cur.remaining'),10,'exclude from cumulative balance');

for(const source of [
  'r.annualEvents=[{date:sat,hours:3}]',
  'r.days=[{date:sat,wk:"六",kind:"rest",status:"annual",hours:3}]',
  'r.absChoice[sat]={type:"annual",hours:3}',
]){
  run('var o=fixture({work:false}); (({r})=>{'+source+'})(o); c=live(o)');
  assert.deepEqual(read('values(c)'),[0,0,10,0]);
  assert.equal(run('c.settlementBlocked'),true);
  assert.equal(run('setConfirm(o.e.id,true)'),false);
  assert.equal(run('payrollReadyForOutput(false)'),false);
}
run('o=fixture({work:false,noBalance:true});o.r.annualEvents=[{date:sat,hours:3}];c=live(o)');
assert.deepEqual(read('values(c)'),[0,0,0,0]);
assert.equal(run('c.reviews.some(x=>x.key==="annualShort")'),false);
run('o=fixture({work:false});o.r.absChoice[sat]={type:"personal",hours:3};c=live(o)');
assert.deepEqual(read('values(c)'),[0,0,10,0]);
assert.equal(run('c.leave.personal'),0);
assert.equal(run('c.settlementBlocked'),true);
run('o=fixture({work:false});o.r.annualEvents=[{date:mon,hours:2}];c=live(o)');
assert.equal(run('c.annualLeft'),9.75,'normal workday leave still counts');
assert.equal(run('c.settlementBlocked'),false);
run('o=fixture();setReview(o.e.id,"ot","ok");c=live(o)');
assert.deepEqual(read('values(c)'),[1,200,10,0]);
run('verifiedLeaveClose(curYM(),{pending:0,needsProof:0,approved:0,unknown:0},Date.now())');
assert.equal(run('setConfirm(o.e.id,true)'),true);
assert.equal(run('payrollReadyForOutput(false)'),true);
run('const savedSnapshot=JSON.stringify(o.r.snapshot);o.r.annualEvents=[{date:sat,hours:2}];');
assert.equal(run('JSON.stringify(compute(o.e,ym))===JSON.stringify({...JSON.parse(savedSnapshot),confirmed:true,locked:true})'),true);
assert.equal(run('JSON.stringify(o.r.snapshot)===savedSnapshot'),true);
run('o=fixture({academic:true});o.r.annualEvents=[{date:sat,hours:2}];c=live(o)');
assert.equal(run('c.settlementBlocked'),true);
assert.equal(run('setConfirm(o.e.id,true)'),false);
console.log('PASS: contracted non-academic rest-day leave preserves source and balance, hard-blocks settlement, preserves no-leave and locked-snapshot paths.');
