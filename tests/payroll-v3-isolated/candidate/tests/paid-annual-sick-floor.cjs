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

const annual = "r.annualEvents=[{date:'2026-11-04',hours:8}];";
check('paid annual and sick same month retains minimum normal wage',calc({sick:8},{base:26500},annual,"[c.net,c.earnings.find(x=>x[0]==='病假最低工資補足')[1],c.deducts.find(x=>x[0]==='事假扣薪')[1]]"),[29009,99,0]);
check('paid annual needs explicit floor acknowledgment',calc({sick:8},{base:26500},annual,"[c.settlementBlocked,c.reviews.find(x=>x.key==='sickFloor').st]"),[true,'pending']);
check('paid annual no unsupported-mixed block after individual acknowledgment',calc({sick:8},{base:26500},annual+"const v=computeLive(e,'2026-11',r).reviews.find(x=>x.key==='sickFloor');r.reviews.sickFloor={d:'ok',v:v.sig};",'[c.net,c.settlementBlocked]'),[29009,false]);
check('paid annual cannot use floor override to underpay',calc({sick:8},{base:26500},annual+"r.overrides['病假最低工資補足']=0;",'c.settlementBlocked'),true);
check('paid annual plus personal still blocked',calc({sick:8,personal:8},{base:26500},annual,'c.settlementBlocked'),true);
check('paid annual plus overtime still blocked',calc({sick:8},{base:26500},annual+"r.otEvents=[{date:'2026-11-02',type:'weekday',hours:1}];",'c.settlementBlocked'),true);
check('paid annual plus partial month still blocked',calc({sick:8},{base:26500,hire:'2026-11-02'},annual,'c.settlementBlocked'),true);
check('high salary annual and sick no floor top up',calc({sick:8},{base:30000},annual,"[c.net,c.earnings.find(x=>x[0]==='病假最低工資補足')[1]]"),[32352,0]);
check('paid annual history snapshot unchanged',calc({sick:8},{base:26500},annual+"r.confirmed=true;r.snapshot={net:7654,dw:1000};","[compute(e,\'2026-11\').net,r.snapshot.dw]"),[7654,1000]);
const ackAll="for(let i=0;i<3;i++)for(const v of computeLive(e,'2026-11',r).reviews)r.reviews[v.key]={d:'ok',v:v.sig};";
for(const label of ['生理假扣薪','事假扣薪','曠職扣薪','颱風假扣薪','遲到/早退扣薪']){
  check('manual '+label+' cannot bypass source absence gate',calc({sick:8},{base:26500},annual+`r.overrides[${JSON.stringify(label)}]=500;`+ackAll,'c.settlementBlocked'),true);
  check('zero '+label+' does not invent missing absence',calc({sick:8},{base:26500},annual+`r.overrides[${JSON.stringify(label)}]=0;`+ackAll,'c.settlementBlocked'),false);
}
check('all negative standard overrides block floor settlement',`(()=>{const labels=[...EARN,...DED];return labels.every(label=>{const e=testEmp({base:26500,perfect:3000,hire:'2024-01-01'}),r=blankRec();r.att.sick=8;${annual}r.overrides[label]=-1;runCase(e,r);${ackAll}return computeLive(e,'2026-11',r).settlementBlocked;})})()`,true);
check('all invalid standard overrides block floor settlement',`(()=>{const labels=[...EARN,...DED];return labels.every(label=>{const e=testEmp({base:26500,perfect:3000,hire:'2024-01-01'}),r=blankRec();r.att.sick=8;${annual}r.overrides[label]='invalid';runCase(e,r);${ackAll}return computeLive(e,'2026-11',r).settlementBlocked;})})()`,true);
check('all nonfinite standard overrides block floor settlement',`(()=>{const labels=[...EARN,...DED];return labels.every(label=>{const e=testEmp({base:26500,perfect:3000,hire:'2024-01-01'}),r=blankRec();r.att.sick=8;${annual}r.overrides[label]=Infinity;runCase(e,r);${ackAll}return computeLive(e,'2026-11',r).settlementBlocked;})})()`,true);
check('legitimate insurance deduction is not wage underpayment',calc({sick:8},{base:26500},annual+"r.overrides['勞保費']=500;"+ackAll,'[c.net,c.settlementBlocked]'),[28509,false]);
check('clearing extra absence restores individual-review path',calc({sick:8},{base:26500},annual+"r.overrides['事假扣薪']=500;"+ackAll+"delete r.overrides['事假扣薪'];","c.reviews.find(x=>x.key===\'sickFloor\').st"),'pending');
console.log(passed+' paid annual sick floor synthetic assertions passed');
