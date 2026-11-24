'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync(require('node:path').join(__dirname,'../index.html'),'utf8').split('<script>')[1].split('</script>')[0];
const end=src.indexOf('function bootUI()');
assert(end>0);
const node={appendChild(){},addEventListener(){},querySelectorAll(){return[]},classList:{add(){},remove(){}},style:{}};
const context={document:{createElement:()=>({}),getElementById:()=>node,addEventListener(){},querySelectorAll:()=>[],querySelector:()=>node},window:{addEventListener(){}},localStorage:{getItem:()=>null},console,TextEncoder,TextDecoder,setTimeout,clearTimeout,setInterval,clearInterval,Intl,location:{origin:'http://127.0.0.1'}};
vm.createContext(context);
vm.runInContext(src.slice(0,end),context);
const setup=`(ym, patch={}, employee={})=>{
 state={version:3,settings:DEF_SETTINGS(),employees:[],months:{}};
 const e={id:'fixture',name:'合成測試',payType:'monthly',base:36000,perfect:0,summer:0,otFixed:0,labor:0,health:0,fixedItems:[],hire:'2024-01-01',leaveSystem:'cal',yearEnd:'pay',sched:defaultSched()};
 Object.assign(e,employee);
 const r=blankRec();r.schoolPay={ym,mode:'academic',start:'',end:'',allowance:4000,attendance:0,cut:0,basis:'合成資料',fridays:[],bonus:null,bonusNote:'',bonusBasis:'',...patch};
 state.employees.push(e);state.months[ym]={[e.id]:r};return {e,r:mrec(e.id,ym)};
}`;
vm.runInContext('const setup='+setup+'; const earningValue=(c,l)=>c.earnings.find(x=>x[0]===l)?.[1]; const event=(date,hours=3,type="rest")=>({date,hours,type});',context);
const run=s=>vm.runInContext(s,context);
const read=s=>JSON.parse(run('JSON.stringify('+s+')'));
node.value='2026';
const byId={pYear:{value:'2026'},pMonth:{value:'8'},parseMsg:{innerHTML:''}};
context.document.getElementById=id=>byId[id]??node;
run(`
const ym='2026-08', sat='2026-08-01', key='restShort:'+sat;
let messages=[];
save=()=>{};renderSlips=renderAtt=openAbs=()=>{};toast=s=>messages.push(s);
localDB.ready=true;
function getRest({mode='academic',date=sat,start='09:00',end='12:00',arrival='10:00',departure='12:00',note='WH=02H00'}={}){
 const {e,r}=setup(ym,{mode,attendance:1000,cut:1000},{empNo:'S001',base:35000,perfect:1000,hourBasis:'punch',lateePolicy:'annualOffset'});
 e.sched.d6={type:'rest',start,end};
 const rows=[['員工編號','中文姓名','日期','打卡','備註'],['S001','合成測試',date,arrival,''],['','',date,departure,note]];
 ingestRows(rows,'synthetic-punch.xlsx');
 if(!commitAttendanceImport())throw Error(byId?.parseMsg?.innerHTML??'import rejected');
 return {e,r:mrec(e.id,ym)};
}
const result=(e,r)=>computeLive(e,ym,r);
const rv=(c)=>c.reviews.find(x=>x.key===key);
const vals=c=>[c.gross,c.ot.rest,earningValue(c,'全勤獎金'),earningValue(c,'休息日定額加班費'),c.late.totalMin,c.absence.offsetH,c.deducts.find(x=>x[0]==='事假扣薪')[1],c.deducts.find(x=>x[0]==='遲到/早退扣薪')[1]];
const first=getRest();let c=result(first.e,first.r);
`);
assert.deepEqual(read('vals(c)'),[40000,2,1000,4000,0,0,0,0]);
assert.deepEqual(read('c.restShort.map(x=>[x.date,x.late,x.early,x.status])'),[['2026-08-01',60,0,'pending']]);
assert.equal(read('c.settlementBlocked'),true);
assert.equal(read('setConfirm(first.e.id,true)'),false);
assert.match(read('reviewBlock(first.e,c)'),/核實個人未出勤/);
run('approveAll(first.e.id);c=result(first.e,first.r)');
assert.equal(read('rv(c).st'),'pending');
run('setReview(first.e.id,key,"personal");c=result(first.e,first.r)');
assert.deepEqual(read('vals(c)'),[39000,2,0,4000,0,0,0,0]);
assert.equal(read('rv(c).st'),'personal');
assert.equal(read('c.leave.personal'),0);
assert.equal(read('usageItems(first.e,Date.UTC(2026,8,1)).filter(x=>x.kind==="late").length'),0);
run('first.r.lateEvents=[{date:sat,late:60,early:0}];c=result(first.e,first.r)');
assert.deepEqual(read('vals(c)'),[39000,2,0,4000,0,0,0,0]);
run('setReview(first.e.id,key,"excused");c=result(first.e,first.r)');
assert.deepEqual(read('vals(c)'),[40000,2,1000,4000,0,0,0,0]);
run('first.r.days[0].in="09:50";first.r.days[0].wh=130;c=result(first.e,first.r)');
assert.deepEqual(read('c.restShort.map(r=>[r.late,r.status])'),[[50,'pending']]);
run('first.r.days[0].in="09:00";first.r.days[0].wh=180;c=result(first.e,first.r)');
assert.deepEqual(read('[c.restShort.length,c.gross,c.ot.rest,c.late.totalMin]'),[0,40000,3,0]);
run('const short=getRest({arrival:"09:01",departure:"11:59",note:"WH=02H58"});setReview(short.e.id,key,"personal");c=result(short.e,short.r)');
assert.deepEqual(read('[c.restShort[0].late,c.restShort[0].early,c.gross]'),[1,1,39000]);
run('short.r.days.push({...short.r.days[0],kind:"work",status:"carePersonal",hours:1});c=result(short.e,short.r)');
assert.deepEqual(read('[c.restShort.length,c.gross,earningValue(c,"全勤獎金")]'),[0,40000,1000]);
run('const absent=getRest({note:"*WH=02H00"});c=result(absent.e,absent.r)');
assert.equal(read('c.restShort.length'),0);
run('const once=getRest({departure:""});c=result(once.e,once.r)');
assert.equal(read('c.restShort.length'),0);
run('const admin=getRest({mode:"standard"});c=result(admin.e,admin.r)');
assert.equal(read('c.restShort.length'),0);
run('const off=getRest({start:"",end:""});c=result(off.e,off.r)');
assert.equal(read('c.restShort.length'),0);
run('const vacation=getRest();Object.assign(vacation.r.schoolPay,{start:sat,end:"2026-08-31"});c=result(vacation.e,vacation.r)');
assert.equal(read('c.restShort.length'),0);
run('const hol=getRest();state.settings.holidays=sat;hol.r.lateEvents=[{date:sat,late:60}];c=result(hol.e,hol.r)');
assert.deepEqual(read('[c.restShort.length,c.late.totalMin,earningValue(c,"全勤獎金")]'),[0,0,1000]);
for(const extra of [
 'r.annualEvents=[{date:sat,hours:1}]',
 'r.absChoice[sat]={type:"carePersonal",hours:1}',
 'r.days[0].punches=1',
 'e.sched.d6.end=""',
 'e.sched.d6.type="work"',
 'e.sched.d6={type:"rest",start:"10:00",end:"12:00"}',
 'r.days.push({...r.days[0]})'
]){
 const expression='(()=>{const {e,r}=getRest();r.lateEvents=[{date:sat,late:60}];'+extra+';const q=result(e,r);return [q.restShort.length,q.late.totalMin,earningValue(q,"全勤獎金")];})()';
 assert.deepEqual(read(expression),[0,0,1000],extra);
}
for(const extra of ['r.days[0].wh=0','e.hourBasis="sched"']){
 const expression='(()=>{const {e,r}=getRest();'+extra+';const q=result(e,r);return [q.restShort.length,q.restShort[0].actualOK,q.leavePayrollBlocks.some(x=>x.includes("未確認實際計薪工時"))];})()';
 assert.deepEqual(read(expression),[1,false,true],extra);
}
run('const lock=getRest();lock.r.confirmed=true;lock.r.snapshot={gross:12345,restShort:[{date:sat,status:"excused"}]};setReview(lock.e.id,key,"personal")');
assert.deepEqual(read('[compute(lock.e,ym).gross,compute(lock.e,ym).restShort[0].status,lock.r.reviews[key]??null]'),[12345,'excused',null]);
run(`
const payKey='schoolRestReduction';
const plan=(r,from=sat)=>Object.assign(r.schoolPay,{restReduceFrom:from,restReduceBasis:'合成書面約定'});
const reduction=()=>{const o=getRest();plan(o.r);setReview(o.e.id,key,'personal');return o;};
const cr=(o)=>result(o.e,o.r);
const apply=(o)=>setReview(o.e.id,payKey,'ok');
const rd=(o)=>cr(o).restReduction;
const red=reduction();
`);
assert.deepEqual(read('vals(cr(red))'),[39000,2,0,4000,0,0,0,0]);
assert.deepEqual(read('[rd(red).minutes,rd(red).proposed,rd(red).rate,rd(red).floor,rd(red).status]'),[60,267,4000/15,389,'pending']);
assert.equal(read('cr(red).settlementBlocked'),true);
assert.match(read('reviewBlock(red.e,cr(red))'),/確認依約減發/);
run('approveAll(red.e.id)');
assert.equal(read('rd(red).status'),'pending');
run('apply(red)');
assert.deepEqual(read('vals(cr(red))'),[38733,2,0,3733,0,0,0,0]);
assert.equal(read('rd(red).applied'),267);
run('setReview(red.e.id,payKey,"no")');
assert.equal(read('cr(red).gross'),39000);
run('apply(red);red.e.base=36000');
assert.deepEqual(read('[rd(red).status,rd(red).proposed,rd(red).applied,cr(red).gross]'),['pending',267,0,40000]);
run('const ahead=reduction();plan(ahead.r,"2026-08-02");apply(ahead)');
assert.deepEqual(read('[rd(ahead),cr(ahead).gross]'),[null,39000]);
run('const excused=reduction();setReview(excused.e.id,key,"excused");apply(excused)');
assert.deepEqual(read('[rd(excused),cr(excused).gross]'),[null,40000]);
run('const invalid=reduction();invalid.r.schoolPay.restReduceFrom="2026-02-30";apply(invalid)');
assert.deepEqual(read('[rd(invalid),cr(invalid).settlementBlocked]'),[null,true]);
run('const fl=reduction();fl.r.otEvents=[8,15,22,29].map((d,i)=>({date:"2026-08-"+String(d).padStart(2,"0"),type:"rest",hours:i===3?.75:5}));fl.r.otEvents.push({date:"2026-08-03",type:"weekday",hours:2});');
assert.deepEqual(read('[rd(fl).floor,rd(fl).proposed,earningValue(cr(fl),"加班費")]'),[3889,111,389]);
run('apply(fl)');
assert.deepEqual(read('[rd(fl).applied,cr(fl).ot.rest,earningValue(cr(fl),"休息日定額加班費"),earningValue(cr(fl),"加班費")]'),[111,17.75,3889,389]);
run('fl.r.otEvents[3].hours=3');
assert.deepEqual(read('[rd(fl).status,rd(fl).applied,earningValue(cr(fl),"休息日定額加班費"),earningValue(cr(fl),"休息日加班補差額")]'),['floor',0,4000,375]);
const winter=read(`(()=>{const y='2026-01',d='2026-01-10',k='restShort:'+d;
 const z=setup(y,{mode:'academic',start:'2026-01-24',end:'2026-01-31',attendance:1000,cut:1000,restReduceFrom:d,restReduceBasis:'合成約定'},{base:35000,perfect:1000,hourBasis:'punch'});
 z.e.sched.d6={type:'rest',start:'09:00',end:'12:00'};
 z.r.days=derivePunch({[d]:{times:['10:00','12:00'],whMin:120}},z.e).days;
 const first=computeLive(z.e,y,z.r),s=first.reviews.find(x=>x.key===k);
 z.r.reviews[k]={d:'personal',v:s.sig};
 const c=computeLive(z.e,y,z.r);
 return [c.restShort[0].status,c.restReduction,c.warns.some(x=>x.includes('本月不減發定額')),c.gross];
})()`);
assert.deepEqual(winter,['personal',null,true,39000]);
console.log('PASS prospective opt-in: exact fixed 15-hour divisor trim, individual preview approval, legal floor rounded up, other OT separate and prior dates/approved exceptions unchanged');
console.log('PASS actual punch-import and individual review: 60 min and 2 h; flat 4000 preserved; one attendance cut, no duplicate deduction/leave; approval staleness and protected cases; confirmed snapshots unchanged');
// Agreed Saturday leave may require affirmative pay. 14h worked gives exactly $4,000;
// the 3rd hour of the fifth agreed shift with eligible sick leave adds ceil(200*5/3/2) = $167.
// A draft may show worked OT only, but confirmation/official output must refuse it.
run(`
const sickDay='2026-08-29', sickKey='restShort:'+sickDay;
const sickFixture=()=>{
 const o=getRest({date:sickDay,arrival:'09:00',departure:'11:00',note:'WH=02H00'});
 o.e.base=48000;Object.assign(o.r.schoolPay,{attendance:0,cut:0});
 o.r.otEvents=[1,8,15,22].map(d=>event('2026-08-'+String(d).padStart(2,'0')));
 plan(o.r);
 return o;
};
let sn=sickFixture();
sn.r.days.push({date:sickDay,wk:'六',kind:'work',status:'sick',hours:1});
let sick=cr(sn);
const sickBlocked=c=>c.leavePayrollBlocks.some(x=>x.includes('休息日約定出勤涉及請假'));
const sickDed=c=>c.deducts.find(x=>x[0]==='病假扣薪')[1];
`);
assert.deepEqual(read('[sick.ot.rest,otPayDay("rest",2,200,false)+4*otPayDay("rest",3,200,false),Math.ceil(4000+otPayDay("rest",3,200,false)/2-otPayDay("rest",2,200,false)/2-1e-8),sickDed(sick),sick.restReduction,sickBlocked(sick)]'),[14,4000,4167,0,null,true]);
assert.equal(read('earningValue(sick,"休息日定額加班費")'),4000);
assert.match(read('payrollBlockReason(sick)'),/全勤.*不可確認或正式出單/);
run('approveAll(sn.e.id);setReview(sn.e.id,"schoolRules","ok");messages=[]');
assert.equal(read('setConfirm(sn.e.id,true)'),false);
assert.match(read('messages.at(-1)'),/休息日約定出勤涉及請假/);
assert.equal(read('payrollReadyForOutput(false)'),false);
const leaveVariants=[
 'o.r.absChoice[sickDay]={type:"protectedSick",hours:1}',
 'o.r.days=[{date:sickDay,wk:"六",kind:"work",status:"sick",hours:3}]',
 'o.r.days=[{date:sickDay,wk:"六",kind:"rest",status:"paidLeave",hours:3}]',
 'o.r.annualEvents=[{date:sickDay,hours:1}]',
 'setReview(o.e.id,sickKey,"leave")',
];
for(const add of leaveVariants)assert.deepEqual(read('(()=>{const o=sickFixture();'+add+';const c=cr(o);return [sickBlocked(c),sickDed(c),c.restReduction];})()'),[true,0,null],add);
assert.deepEqual(read('(()=>{const o=sickFixture();setReview(o.e.id,sickKey,"excused");o.r.days.push({date:"2026-08-24",wk:"一",kind:"work",status:"sick",hours:1});const c=cr(o);return [sickBlocked(c),sickDed(c),c.restShort[0].status];})()'),[false,100,'excused']);
assert.deepEqual(read(`(()=>{const y='2026-01',d='2026-01-10';
 const o=setup(y,{start:'2026-01-24',end:'2026-01-31',restReduceFrom:d,restReduceBasis:'約定'},{base:48000,hourBasis:'punch'});
 o.e.sched.d6={type:'rest',start:'09:00',end:'12:00'};
 o.r.days=derivePunch({[d]:{times:['09:00','11:00'],whMin:120}},o.e).days;
 o.r.days.push({date:d,wk:'六',kind:'work',status:'sick',hours:1});
 const c=computeLive(o.e,y,o.r);return [sickBlocked(c),sickDed(c),c.ot.rest,c.restReduction];
})()`),[true,0,2,null]);
console.log('PASS $4,167 eligible sick-leave scenario enters explicit non-overridable settlement hold; 14 worked hours, no ordinary sick deduction or flat-pay trim; weekdays and winter priority regressions covered');
// The contractual divisor stays at 15 in both 4- and 5-Saturday months; only legal OT uses normal wage.
for(const [ym,day,saturdays] of [['2026-08','2026-08-01',5],['2026-09','2026-09-05',4]]){
 for(const [late,inTime,wh,reduction] of [[1,'09:01',179,4],[15,'09:15',165,67],[30,'09:30',150,133],[60,'10:00',120,267],[90,'10:30',90,400]]){
  const got=read(`(()=>{
    const y='${ym}',d='${day}',o=setup(y,{attendance:0,cut:0,restReduceFrom:d,restReduceBasis:'合成約定'});
    o.e.hourBasis='punch';o.e.sched.d6={type:'rest',start:'09:00',end:'12:00'};
    o.r.days=derivePunch({[d]:{times:['${inTime}','12:00'],whMin:${wh}}},o.e).days;
    const k='restShort:'+d,first=computeLive(o.e,y,o.r),rv=first.reviews.find(x=>x.key===k);
    o.r.reviews[k]={d:'personal',v:rv.sig};
    const c=computeLive(o.e,y,o.r),z=c.restReduction;
    return [Array.from({length:31},(_,i)=>y+'-'+String(i+1).padStart(2,'0')).filter(d=>schoolDate(d,y)!=null&&wkOf(d)==='六').length,z.minutes,z.proposed,z.rate,z.contractHours];
  })()`);
  assert.deepEqual(got,[saturdays,late,reduction,4000/15,15]);
 }
}
assert.deepEqual(read(`(()=>{
 const o=getRest({arrival:'09:01',note:'WH=02H59'}),d='2026-08-08',k='restShort:'+d;
 plan(o.r);o.r.days.push(derivePunch({[d]:{times:['09:01','12:00'],whMin:179}},o.e).days[0]);
 setReview(o.e.id,key,'personal');setReview(o.e.id,k,'personal');apply(o);
 const c=cr(o);return [c.restReduction.minutes,c.restReduction.applied,earningValue(c,'休息日定額加班費')];
})()`),[2,9,3991]);
console.log('PASS 15-hour divisor stays fixed across both calendar counts; five minute fixtures; monthly aggregation before nearest-dollar rounding');
const rules=read(`(()=>{const o=getRest();return schoolPayBlock(o.e,cr(o));})()`);
for(const pattern of [/百宏薪資規則｜全勤、休息日加班/,/方式二｜按約定 15 小時比例減發/,/未啟用（生效日與書面依據皆留空/,/該員工本月原定休息日定額加班費 ÷ 5 個週六 ÷ 每次 3 小時 × 核實未出勤分鐘 ÷ 60/,/60 分鐘為 267 元.*3,733 元/,/受保護的假別，不自動減發/,/同一範圍.*法定加班費.*補差額/,/全勤依其規則另計，不重扣底薪/,/1、2 月含寒假.*本月不套用/,/name="restReduceFrom" value=""/, /name="restReduceBasis" maxlength="220" value=""/])assert.match(rules,pattern);
assert.match(read(`(()=>{const o=getRest();plan(o.r);return schoolPayBlock(o.e,cr(o));})()`),/已填書面約定與生效日（仍須逐筆核對）/);
console.log('PASS in-app rules state the method, unchanged default, formula, statutory floor/top-up, protected statuses, and winter exclusion');
for(const [fixed,trim] of [[3000,200],[4000,267],[4500,300],[5000,333]]){
 const calc=read(`(()=>{const o=getRest();o.r.schoolPay.allowance=${fixed};plan(o.r);setReview(o.e.id,key,'personal');apply(o);const c=cr(o);
  return [c.restReduction.rate,c.restReduction.original,c.restReduction.applied,earningValue(c,'休息日定額加班費')];
 })()`);
 assert.deepEqual(calc,[fixed/15,fixed,trim,fixed-trim]);
}
assert.deepEqual(read(`(()=>{const o=getRest();o.r.schoolPay.allowance=0;plan(o.r);setReview(o.e.id,key,'personal');apply(o);const c=cr(o);
 return [c.restReduction,earningValue(c,'休息日定額加班費'),earningValue(c,'休息日加班補差額')];
})()`),[null,0,389]);
assert.deepEqual(read(`(()=>{const o=getRest();delete o.r.schoolPay.allowance;plan(o.r);setReview(o.e.id,key,'personal');const c=cr(o);
 return [c.restReduction,c.settlementBlocked,earningValue(c,'休息日定額加班費')];
})()`),[null,true,0]);
assert.deepEqual(read(`(()=>{const o=getRest();Object.assign(o.r.schoolPay,{start:'2026-08-16',end:'2026-08-31',allowance:5000});plan(o.r);setReview(o.e.id,key,'personal');apply(o);const c=cr(o);
 return [c.restReduction.contractAmount,c.restReduction.applied,earningValue(c,'寒暑期教學津貼'),earningValue(c,'休息日定額加班費')];
})()`),[2419,161,2581,2258]);
assert.deepEqual(read(`(()=>{const o=reduction();apply(o);o.r.schoolPay.allowance=4500;const c=cr(o);
 return [c.restReduction.status,c.restReduction.applied,c.restReduction.proposed,earningValue(c,'休息日定額加班費'),c.settlementBlocked];
})()`),['pending',0,300,4500,true]);
console.log('PASS contracted monthly amounts 3000/4000/4500/5000, zero and invalid amount do not fall back, summer split uses only fixed component, amount change invalidates approval');
// Compare only the covered scope. No jump to a compliance verdict before relevant facts are known.
assert.match(read('(()=>{const o=reduction();apply(o);return cr(o).otNote;})()'),/定額 3,733 元.*底線 389 元：高於法定底線 3,344 元/);
const floorResults=read(`(()=>{
 const o=reduction();o.r.otEvents=[8,15,22,29].map((d,i)=>event('2026-08-'+String(d).padStart(2,'0'),i===3?.75:5));
 o.r.otEvents.push(event('2026-08-03',2,'weekday'));
 const draft=cr(o).otNote;apply(o);const equal=cr(o).otNote;
 o.r.otEvents[3].hours=3;const low=cr(o);
 return [draft,equal,low.otNote,earningValue(low,'休息日加班補差額'),earningValue(low,'加班費')];
})()`);
assert.match(floorResults[0],/按比例算 267 元，依底線最多減發 111 元/);
assert.match(floorResults[1],/定額 3,889 元.*底線 3,889 元：等於法定底線，按此金額計已足額.*其他加班 389 元另計/);
assert.match(floorResults[2],/定額 4,000 元.*底線 4,375 元：不足，須另補 375 元.*其他加班 389 元另計/);
assert.deepEqual(floorResults.slice(3),[375,389]);
assert.match(read('sick.otNote'),/底線 4,000 元：待核對，不能判定是否足額/);
assert.doesNotMatch(read('sick.otNote'),/高於法定底線|等於法定底線/);
assert.match(read('(()=>{const o=getRest();return cr(o).otNote;})()'),/待核對/);
assert.match(read(`(()=>{
 const o=getRest({arrival:'09:00',note:'WH=03H00'});o.e.base=48000;Object.assign(o.r.schoolPay,{attendance:0,cut:0,allowance:3934});
 o.r.otEvents.push(event('2026-08-08',9));const c=cr(o);return c.otNote;
})()`),/定額 3,934 元.*底線 3,934 元：等於法定底線/);
assert.match(rules,/第 9–12 小時 × 8\/3.*勞基法第 24 條/);
console.log('PASS statutory floor outcomes, clamping and mandatory top-up, 9th hour tier, other overtime isolated, unresolved paid leave gives no false positive');
