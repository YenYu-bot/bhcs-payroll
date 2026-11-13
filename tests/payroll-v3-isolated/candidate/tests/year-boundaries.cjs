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


function yearCase(ym,props={},att={}){return `(()=>{const e=testEmp(${JSON.stringify(props)}),r=blankRec();Object.assign(r.att,${JSON.stringify(att)});runCase(e,r,${JSON.stringify(ym)});const c=computeLive(e,${JSON.stringify(ym)},r);return {net:c.net,blocked:c.settlementBlocked,warns:c.warns,floor:c.earnings.find(x=>x[0]==='病假最低工資補足')[1],reviews:c.reviews.map(x=>x.key)}})()`;}
check('2026 standards',"minimumWageFor('2026-12')",{month:29500,hour:196});
check('2027 standards',"minimumWageFor('2027-01')",{month:30900,hour:205});
check('unknown year no fallback',"minimumWageFor('2028-01')",null);
check('invalid month no fallback',"minimumWageFor('2027-13')",null);
check('2026 no new calendar gate',`(${yearCase('2026-11')}).blocked`,false);
check('2027 calendar missing blocks even high salary',`(${yearCase('2027-01')}).blocked`,true);
check('2027 monthly low wage warning',`(${yearCase('2027-01',{base:30000})}).warns.some(x=>x.includes('30,900'))`,true);
check('2027 hourly low wage warning',`(${yearCase('2027-01',{payType:'hourly',rate:200})}).warns.some(x=>x.includes('205'))`,true);
check('2027 sick floor updated',`(${yearCase('2027-01',{base:27900,perfect:3000},{sick:8})}).net`,30385);
check('2027 full month old labor requires bill',`(${yearCase('2027-01',{labor:795,laborGrade:31800})}).reviews.includes('laborPrecision')`,true);
check('manual insurance mode cannot evade year gate',`(${yearCase('2027-01',{labor:795,laborGrade:31800,insAuto:false})}).reviews.includes('laborPrecision')`,true);
check('zero amount known labor grade cannot evade',`(${yearCase('2027-01',{labor:0,laborGrade:31800})}).reviews.includes('laborPrecision')`,true);
check('2027 pension full month needs bill',`(${yearCase('2027-01',{pensionWage:31800})}).reviews.includes('pensionPrecision')`,true);
check('2027 all acknowledgment cannot evade missing calendar',`(()=>{const e=testEmp(),r=blankRec();runCase(e,r,'2027-01');for(const x of computeLive(e,'2027-01',r).reviews)r.reviews[x.key]={d:'ok',v:x.sig};return computeLive(e,'2027-01',r).settlementBlocked})()`,true);
check('historical confirmed snapshot untouched',`(()=>{const e=testEmp(),r=blankRec();runCase(e,r,'2027-01');r.confirmed=true;r.snapshot={net:7654};return compute(e,'2027-01').net})()`,7654);
console.log(passed+' year-boundary synthetic assertions passed');
