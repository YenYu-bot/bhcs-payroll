// Synthetic numerical fixtures. Differential equality is not a legal or calculation-correctness sign-off.
const fs=require('fs'),vm=require('vm');
const elements={};const el=id=>elements[id]||=({value:'',checked:false,innerHTML:'',textContent:'',style:{},dataset:{},classList:{add(){},remove(){},contains(){return false},toggle(){}},addEventListener(){},appendChild(){},querySelectorAll(){return []},querySelector(){return null}});
const doc={getElementById:el,querySelectorAll(){return []},querySelector(){return null},createElement(){return el('anon')},addEventListener(){},body:el('body')};
let script=fs.readFileSync(process.env.PAYROLL_HTML||require('node:path').join(__dirname,'../index.html'),'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
script=script.split('\n').filter(l=>!l.startsWith("if(load()==='locked')")&&!l.startsWith('cloudInit();')).join('\n');
const context=vm.createContext({document:doc,console,localStorage:{getItem(){return null},setItem(){}},window:{},crypto:require('crypto').webcrypto,TextEncoder,TextDecoder,URL,Blob,setTimeout(){},clearTimeout(){},setInterval(){},clearInterval(){},navigator:{}});
vm.runInContext(script,context);
const run=code=>vm.runInContext(code,context);
run(`function testEmp(p={}){return Object.assign({id:'test',name:'合成測試',payType:'monthly',base:36000,rate:200,hire:'2026-01-01',leave:'',labor:0,health:0,perfect:0,summer:0,otFixed:0,fixedItems:[],pensionWage:0,pensionSelf:0,sched:Object.fromEntries(Array.from({length:7},(_,i)=>['d'+i,{type:i===0?'off':i===6?'rest':'work',start:'09:00',end:'17:00'}])),hourBasis:'punch',hourRound:0,brkMin:0,brkAfter:0,leaveSystem:'cal',yearEnd:'pay',lateePolicy:'deduct',lateGrace:0,lateUnit:0},p)};function runCase(e,r,ym='2026-11'){state.settings=DEF_SETTINGS();state.employees=[e];state.months={[ym]:{[e.id]:r}};const c=computeLive(e,ym,r);return {pr:c.pr,earnings:c.earnings.filter(x=>x[1]),deducts:c.deducts.filter(x=>x[1]),ot:c.ot,attend:c.attend,pensionEr:c.pensionEr,warns:c.warns,reviews:c.reviews}};function workDay(date,h,kind='work'){return {date,wk:wkOf(date),status:'work',kind,wh:h*60,punches:2,in:'09:00',out:'19:00'}}`);
const assert=require('node:assert/strict');let passed=0;
function check(name,code,expected){const actual=JSON.parse(JSON.stringify(run(code)));assert.deepEqual(actual,expected,name);passed++;console.log('PASS '+name);}

const value=(kind,label)=>`c.${kind}.find(x=>x[0]==='${label}')[1]`;
function calc(att,props={},extra='',ret='c.net'){return `(()=>{const e=testEmp(${JSON.stringify({base:30000,perfect:3000,hire:'2024-01-01',...props})}),r=blankRec();Object.assign(r.att,${JSON.stringify(att)});runCase(e,r);${extra}const c=computeLive(e,'2026-11',r);return ${ret}})()`;}
check('Q10 normal wage uses actual attendance',calc({sick:8}),32352);
check('Q5 low wage floor',calc({sick:8},{base:26500}),29009);
check('Q5 high bonus floor',calc({sick:8},{base:14500,perfect:15000}),29009);
check('Q10 holiday extra actual attendance',calc({sick:8},{},"r.otEvents=[{date:'2026-11-02',type:'holiday',hours:8}];",'c.ot.pay'),1097);
check('care personal exempt attendance',calc({carePersonal:8},{},'',`[${value('earnings','全勤獎金')},${value('deducts','事假扣薪')}]`),[3000,1100]);
check('protected sick exempt attendance',calc({protectedSick:8},{},'',`[${value('earnings','全勤獎金')},${value('deducts','病假扣薪')}]`),[3000,550]);
check('ordinary personal still cancels',calc({personal:8},{},'',`[${value('earnings','全勤獎金')},${value('deducts','事假扣薪')}]`),[0,1000]);
check('family care remains exempt',calc({family:8},{},'',value('earnings','全勤獎金')),3000);
check('protected included in annual half pay cap',calc({protectedSick:8},{},"const prev=blankRec();prev.att.sick=240;state.months['2026-10']={test:prev};",value('deducts','病假扣薪')),1100);
check('ordinary sick only affects attendance',calc({protectedSick:8,sick:8},{},'',value('earnings','全勤獎金')),2900);
check('protected CSV labels',`[classifyLeave('安胎'),classifyLeave('未滿3月流產'),classifyLeave('照顧家人事假'),classifyLeave('家庭照顧假')]`,['protectedSick','protectedSick','carePersonal','family']);
check('manual protected calendar and absence aggregate',calc({},{},"r.days=[{date:'2026-11-02',wk:'一',status:'protectedSick',hours:4}];r.absChoice={'2026-11-03':{type:'protectedSick',hours:4}};",`[c.leave.sick,c.leave.protectedSick,${value('earnings','全勤獎金')}]`),[1,1,3000]);
check('perfect same dollar new reason invalidates',calc({personal:8},{},"let v=computeLive(e,'2026-11',r).reviews.find(x=>x.key==='perfect');r.reviews.perfect={d:'ok',v:v.sig};r.att.personal=16;",`c.reviews.find(x=>x.key==='perfect').st`),'pending');
check('unpaid same dollar prior changes invalidates',calc({sick:8},{},"const prev=blankRec();prev.att.sick=240;state.months['2026-10']={test:prev};let v=computeLive(e,'2026-11',r).reviews.find(x=>x.key==='sickUnpaid');r.reviews.sickUnpaid={d:'ok',v:v.sig};prev.att.sick=248;",`c.reviews.find(x=>x.key==='sickUnpaid').st`),'pending');
check('floor negative override blocked',calc({sick:8},{base:26500},"r.overrides['病假最低工資補足']=0;",'c.settlementBlocked'),true);
check('mixed low wage not silently certified',calc({sick:8,personal:8},{base:26500},'','c.settlementBlocked'),true);
check('existing snapshot unchanged',`(()=>{const e=testEmp(),r=blankRec();runCase(e,r);r.confirmed=true;r.snapshot={net:55,dw:1000};r.att.protectedSick=8;return [compute(e,'2026-11').net,r.snapshot.dw]})()`,[55,1000]);
check('original annual daily reference preserved',calc({sick:8},{},'','c.dw'),1100);
check('no spurious unpaid review with zero excess',calc({},{},'',"c.reviews.some(x=>x.key==='sickUnpaid')"),false);
check('fractional attendance deduction never exceeds proportion',calc({sick:4},{perfect:100},'',value('earnings','全勤獎金')),99);
const partSetup=`const e=testEmp({payType:'hourly',rate:200,ptRatio:.5,perfect:0,hire:'2024-01-01'}),r=blankRec();for(let i=0;i<7;i++)e.sched['d'+i]={type:'work',start:'09:00',end:'13:00'};runCase(e,r);for(const m of ['08','09','10']){const p=blankRec();p.days=[{date:'2026-'+m+'-03',wk:wkOf('2026-'+m+'-03'),status:'menstrual',hours:4}];state.months['2026-'+m]={test:p};}state.months['2026-08'].test.att.sick=120;r.days=[{date:'2026-11-03',wk:'二',status:'menstrual',hours:4}];`;
check('part time fourth calendar day no extra half pay',`(()=>{${partSetup}const c=computeLive(e,'2026-11',r);return [c.earnings.find(x=>x[0]==='病假/生理假半薪')[1],c.leave.sickFullDays,c.settlementBlocked]})()`,[0,.5,false]);
check('part time first three retain half pay',`(()=>{${partSetup}delete state.months['2026-10'];const c=computeLive(e,'2026-11',r);return [c.earnings.find(x=>x[0]==='病假/生理假半薪')[1],c.settlementBlocked]})()`,[400,false]);
check('legacy menstrual missing dates blocks',calc({menstrual:4},{payType:'hourly',ptRatio:.5},'','c.settlementBlocked'),true);
check('confirmed history not rewritten by menstrual allocation',`(()=>{${partSetup}const p=state.months['2026-08'].test;p.confirmed=true;p.snapshot={net:77};p.days=[];p.att.menstrual=4;const before=JSON.stringify(p);const c=computeLive(e,'2026-11',r);return [c.settlementBlocked,JSON.stringify(p)===before]})()`,[true,true]);
check('same day duplicate menstrual blocks',`(()=>{${partSetup}r.absChoice={'2026-11-03':{type:'menstrual',hours:4}};return computeLive(e,'2026-11',r).settlementBlocked})()`,true);
check('wrong month menstrual date blocks',`(()=>{${partSetup}r.days[0].date='2026-12-03';return computeLive(e,'2026-11',r).settlementBlocked})()`,true);
// Fixture has no 2027 annual mapping/month review; pay resets but independent calendar gate blocks.
check('next calendar year resets dates',`(()=>{${partSetup}const p=blankRec();p.days=[{date:'2027-01-04',wk:'一',status:'menstrual',hours:4}];state.months['2027-01']={test:p};const c=computeLive(e,'2027-01',p);return [c.earnings.find(x=>x[0]==='病假/生理假半薪')[1],c.settlementBlocked]})()`,[400,true]);
check('partial scheduled day not guessed',`(()=>{${partSetup}r.days[0].hours=2;return computeLive(e,'2026-11',r).settlementBlocked})()`,true);
check('minimum floor explicit review cannot batch approve',calc({sick:8},{base:26500},"curYM=()=> '2026-11';save=()=>{};renderSlips=()=>{};toast=()=>{};approveAll(e.id);", "[c.reviews.find(x=>x.key==='sickFloor').st,setConfirm(e.id,true)]"),['pending',false]);
check('menstrual incomplete blocks final output',calc({menstrual:4},{payType:'hourly'},"curYM=()=> '2026-11';toast=()=>{};",'[setConfirm(e.id,true),payrollReadyForOutput()]'),[false,false]);
check('low wage sick plus OT requires floor basis review',calc({sick:8},{base:26500},"r.otEvents=[{date:'2026-11-02',type:'weekday',hours:1}];",'c.settlementBlocked'),true);
check('absence ordinary approve all settles once',calc({},{},"r.days=[{date:'2026-11-02',wk:'一',status:'absent',hours:8}];curYM=()=> '2026-11';save=()=>{};renderSlips=()=>{};toast=()=>{};approveAll(e.id);",`[c.pendingReviews,c.reviews.find(x=>x.key==='absent').amt]`),[0,1000]);
check('actual perfect override floor only needs 1',calc({sick:8},{base:26500},"r.overrides['全勤獎金']=3000;",`[c.net,${value('earnings','病假最低工資補足')}]`),[29009,1]);
check('base override no stale floor and blocks wage basis',calc({sick:8},{base:26500},"r.overrides['底薪']=27000;",`[${value('earnings','病假最低工資補足')},c.settlementBlocked]`),[0,true]);
check('floor pending blocks output',calc({sick:8},{base:26500},"curYM=()=> '2026-11';toast=()=>{};",'[c.settlementBlocked,payrollReadyForOutput()]'),[true,false]);
check('individual floor acknowledgment unblocks output',calc({sick:8},{base:26500},"curYM=()=> '2026-11';toast=()=>{};const v=computeLive(e,'2026-11',r).reviews.find(x=>x.key==='sickFloor');r.reviews.sickFloor={d:'ok',v:v.sig};",'[c.settlementBlocked,payrollReadyForOutput()]'),[false,true]);
check('override note identifies actual amount, not extra automatic deduction',calc({sick:8},{base:26500},"r.overrides['全勤獎金']=3000;", "[c.perfectStatus,c.perfectNote.includes('3,000 元實發'),c.perfectNote.includes('不再另扣'),c.reviews.find(x=>x.key==='perfect').label.includes('不另扣薪'),c.net]"),['manual',true,true,true,29009]);
check('part time unpaid footer shows 15 day half-pay cap',`(()=>{${partSetup}const c=computeLive(e,'2026-11',r);return [leaveText(c).includes('15 日（120 小時）'),leaveText(c).includes('30 日')]})()`,[true,false]);
check('old snapshot missing cap never invents 30 days',`leaveText({leave:{sickFullDays:.5}}).includes('依當時核定額度')`,true);
check('floor print reason not deferred annual',calc({sick:8},{base:26500},'',"[payrollBlockReason(c).includes('病假最低工資'),payrollBlockReason(c).includes('特休') ]"),[true,false]);
check('deferred annual print reason retained',`payrollBlockReason({deferredNeeds:[{}],leavePayrollBlocks:[]})`, '遞延特休原年度工資依據待核對');
console.log(passed+' leave type and wage synthetic assertions passed');
