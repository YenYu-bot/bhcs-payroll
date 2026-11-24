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
get('pYear').value='2027';get('pMonth').value='1';get('encoding').value='utf-8';
run(`
const types=defaultSched();
const mk=(id,empNo,name)=>({id,empNo,name,sched:types});
state.employees=[mk('x','01','測試同名'),mk('y','02','測試同名'),mk('z','03','測試已確認'),mk('p','04','測試請假'),mk('q','05','測試他人')];
state.months['2027-02']={x:{days:[{date:'old'}]},z:{confirmed:true,snapshot:{net:99},days:[]},p:{days:[{leaveDesk:true}]}};
localDB.ready=true;let writes=0;
save=()=>writes++;renderAtt=openAbs=toast=()=>{};
const head=['員工編號','中文姓名','日期','打卡'];
const punch=[head,['01','測試同名','2027/2/1','09:00'],['','','','17:00'],['02','測試同名','2027-02-01','10:00'],['','','','17:00'],['03','測試已確認','2027-02-01','09:00'],['04','測試請假','2027-02-01','09:00'],['01','測試同名','2027-02-02','09:00'],['','','','17:00']];
const original=JSON.stringify(state);
`);
const msg=()=>get('parseMsg').innerHTML;
run('ingestRows(punch,"<test>.xlsx")');
assert.match(msg(),/尚未寫入.*新增 1 人、覆蓋 1 人、已確認略過 1 人、請假保護略過 1 人/);
assert.match(msg(),/&lt;test&gt;/);
assert.deepEqual(t('attendancePreview.entries.map(x=>[x.eid,x.status,x.dates.length])'),[['x','overwrite',2],['y','add',1],['z','locked',1],['p','protected',1]]);
assert.deepEqual(t('[JSON.stringify(state)===original,curYM(),writes]'),[true,'2027-01',0]);
run('cancelAttendanceImport()');
assert.equal(t('commitAttendanceImport()'),false);
assert.deepEqual(t('[JSON.stringify(state)===original,curYM(),writes]'),[true,'2027-01',0]);
for(const [row,pattern] of [
 [['01','測試他人','2027-02-01','09:00'],/編號與姓名不一致/],
 [['99','測試他人','2027-02-01','09:00'],/不會改以姓名配對/],
 [['','測試同名','2027-02-01','09:00'],/同名/],
 [['01','測試同名','2027-02-30','09:00'],/日期無效/],
 [['01','測試同名','2027-03-01','09:00'],/檔案含多個月份/]
]){
 run('ingestRows([...punch,'+JSON.stringify(row)+'],"bad.xlsx")');
 assert.match(msg(),pattern);
 assert.deepEqual(t('[JSON.stringify(state)===original,attendancePreview,curYM(),writes]'),[true,null,'2027-01',0]);
}
run('ingestRows(punch,"late.xlsx");state.months["2027-02"].x.confirmed=true');
assert.equal(t('commitAttendanceImport()'),false);assert.match(msg(),/預覽已失效/);
run('delete state.months["2027-02"].x.confirmed;ingestRows(punch,"ok.xlsx")');
assert.equal(t('commitAttendanceImport()'),true);
assert.deepEqual(t('[curYM(),writes,state.months["2027-02"].x.days.length,state.months["2027-02"].y.days.length,state.months["2027-02"].p.days[0].leaveDesk,state.months["2027-02"].z.snapshot.net]'),['2027-02',1,2,1,true,99]);
assert.equal(t('commitAttendanceImport()'),false);
run('state.employees.push(mk("dup","01","他人"));ingestRows(punch,"duplicate.xlsx")');
assert.match(msg(),/員工編號重複/);
run('state.employees.pop();');
// Explicit categories cannot fall through to attendance; a valid zero is not missing.
run(`const simpleHead=['員工編號','日期','假別','時數'];const simple=(category,hours)=>[simpleHead,['05','2027-02-04',category,hours]];`);
for(const [category,hours] of [['正堂',4],['',4],['病假待核',4],['正常',0],['曠職',0],['休息日',0],['漏打卡',4],['漏打卡',0]]){
 run('ingestRows(simple('+JSON.stringify(category)+','+hours+'),"1.csv")');
 assert.match(msg(),/無法預覽/);assert.equal(t('attendancePreview'),null);
}
for(const [category,hours,expect] of [['曠職',4,['absent','work',4]],['國定假日',0,['holiday','work',0]],['國定假日出勤',4,['work','holidayWork',4]],['正常出勤',4,['work','work',4]],['特休',0,['annual','work',0]]]){
 run('ingestRows(simple('+JSON.stringify(category)+','+hours+'),"1.csv")');
 assert.deepEqual(t('((d)=>[d.status,d.kind,d.hours])(attendancePreview.entries[0].delta.days[0])'),expect);
}
run('cancelAttendanceImport()');
const enc=s=>{const b=Buffer.from(s);return b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength)};
(async()=>{
 await context.handleFile({name:'flat.csv',arrayBuffer:async()=>enc('員工編號,姓名,日期,假別,時數\n05,測試他人,2027-02-05,正常,5')});
 assert.match(msg(),/尚未寫入/);
 assert.deepEqual(t('[writes,state.months["2027-02"].q??null]'),[1,null]);
 assert.equal(t('commitAttendanceImport()'),true);
 assert.deepEqual(t('[writes,state.months["2027-02"].q.days[0].hours]'),[2,5]);
 context.DecompressionStream=DecompressionStream;
 const bytes=run('buildXlsx("測試", [["員工編號","姓名","日期","假別","時數"],["05","測試他人",46424,"病假",3]])');
 await context.handleFile({name:'flat.xlsx',arrayBuffer:async()=>bytes});
 assert.match(msg(),/尚未寫入/);
 assert.deepEqual(t('[attendancePreview.ym,attendancePreview.entries[0].delta.days[0].status,writes]'),['2027-02','sick',2]);
 let release;
 const reading=context.handleFile({name:'late.csv',arrayBuffer:()=>new Promise(r=>release=r)});
 await context.handleFile({name:'latest.csv',arrayBuffer:async()=>enc('員工編號,姓名,日期,假別,時數\n05,測試他人,2027-02-05,正常,4')});
 release(enc('員工編號,姓名,日期,假別,時數\n05,測試他人,2027-02-03,事假,3'));
 await reading;
 assert.equal(t('attendancePreview.fname'),'latest.csv');
 run('persistence.external=true');
 assert.equal(t('commitAttendanceImport()'),false);
 assert.equal(t('writes'),2);
 console.log('PASS ID-first attendance preview; exact impact and month; fail/cancel/stale atomic; synthetic CSV and XLSX readers; last async read wins');
})().catch(e=>{console.error(e);process.exitCode=1});
