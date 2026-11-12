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


check('59 minutes retained with old 30-min floor', `workedH(testEmp({payType:'hourly',hourRound:30}),workDay('2026-11-02',59/60))`,59/60);
check('14 minutes retained with old 15-min floor', `workedH(testEmp({payType:'hourly',hourRound:15}),workDay('2026-11-02',14/60))`,14/60);
check('monthly overtime minute not discarded', `workedH(testEmp({hourRound:30}),workDay('2026-11-02',8+1/60))`,8+1/60);
const setup=`const e=testEmp({payType:'hourly',rate:200,hourRound:30,hourBasis:'sched',brkMin:60,brkAfter:4}),r=blankRec();e.sched.d1.end='18:00';r.days=[workDay('2026-11-02',9)];runCase(e,r);`;
check('9h schedule less actual 60m rest equals 8h',`(()=>{${setup}return workedH(e,r.days[0])})()`,8);
check('paid leave fallback net schedule equals 8h',`(()=>{${setup}r.days[0].status='paidLeave';return dayAgg(e,r).leaveH.paidLeave})()`,8);
check('manual net hours never deducted twice',`(()=>{${setup}r.days[0].hours=8;return workedH(e,r.days[0])})()`,8);
check('under threshold no deduction',`workedH(testEmp({brkMin:60,brkAfter:4}),workDay('2026-11-02',239/60))`,239/60);
check('threshold deduction once no floor',`workedH(testEmp({brkMin:30,brkAfter:4,hourRound:30}),workDay('2026-11-02',241/60))`,211/60);
check('no punches sched falls back actual',`(()=>{${setup}r.days[0].punches=1;r.days[0].wh=59;return workedH(e,r.days[0])})()`,59/60);
check('blank schedule falls back actual',`(()=>{${setup}e.sched.d1.end='';r.days[0].wh=59;return workedH(e,r.days[0])})()`,59/60);
check('negative absent work never generates negative hours',`workedH(testEmp(),{wh:-1})`,0);
check('59 minute wage rounds only money',`(()=>{${setup}e.hourBasis='punch';e.brkMin=0;r.days[0].wh=59;return computeLive(e,'2026-11',r).earnings.find(x=>x[0]==='工時工資')[1]})()`,197);
check('schedule no fake hour overtime',`(()=>{${setup}const c=computeLive(e,'2026-11',r);return [c.earnings.find(x=>x[0]==='工時工資')[1],c.ot.pay]})()`,[1600,0]);
check('review required and batch cannot approve',`(()=>{${setup}curYM=()=> '2026-11';save=()=>{};renderSlips=()=>{};toast=()=>{};approveAll(e.id);return [computeLive(e,'2026-11',r).reviews.find(x=>x.key==='workMinutes').st,setConfirm(e.id,true)]})()`,['pending',false]);
check('rest change invalidates old review',`(()=>{${setup}let v=computeLive(e,'2026-11',r).reviews.find(x=>x.key==='workMinutes');r.reviews.workMinutes={d:'ok',v:v.sig};e.brkMin=30;return computeLive(e,'2026-11',r).reviews.find(x=>x.key==='workMinutes').st})()`,'pending');
check('same hours date change invalidates review',`(()=>{${setup}let v=computeLive(e,'2026-11',r).reviews.find(x=>x.key==='workMinutes');r.reviews.workMinutes={d:'ok',v:v.sig};r.days[0].date='2026-11-09';return computeLive(e,'2026-11',r).reviews.find(x=>x.key==='workMinutes').st})()`,'pending');
check('rejection cannot restore rounding floor',`(()=>{${setup}let v=computeLive(e,'2026-11',r).reviews.find(x=>x.key==='workMinutes');r.reviews.workMinutes={d:'no',v:v.sig};return computeLive(e,'2026-11',r).reviews.find(x=>x.key==='workMinutes').st})()`,'pending');
check('frozen historical snapshot survives correction',`(()=>{${setup}r.confirmed=true;r.snapshot={net:100};const before=JSON.stringify(r);return [compute(e,'2026-11').net,JSON.stringify(r)===before]})()`,[100,true]);
check('pending work minutes blocks official output',`(()=>{${setup}curYM=()=> '2026-11';toast=()=>{};return [computeLive(e,'2026-11',r).settlementBlocked,payrollReadyForOutput()]})()`,[true,false]);
check('individual acknowledgment releases output',`(()=>{${setup}curYM=()=> '2026-11';toast=()=>{};const v=computeLive(e,'2026-11',r).reviews.find(x=>x.key==='workMinutes');r.reviews.workMinutes={d:'ok',v:v.sig};return [computeLive(e,'2026-11',r).settlementBlocked,payrollReadyForOutput()]})()`,[false,true]);
console.log(passed+' hourly-boundary assertions passed');
