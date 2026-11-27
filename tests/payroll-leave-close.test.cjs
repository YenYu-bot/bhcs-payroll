'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../index.html'),'utf8').split('<script>')[1].split('</script>')[0];
const inputs={pYear:{value:'2026'},pMonth:{value:'11',appendChild(){}}};
const context=vm.createContext({document:{createElement:()=>({}),getElementById:k=>inputs[k]??{value:'',addEventListener(){}},addEventListener(){}},window:{addEventListener(){}},Intl,console,setTimeout,clearTimeout});
const run=s=>vm.runInContext(s,context);
run(source.slice(0,source.indexOf('function bootUI()')));
inputs.pYear.value='2026';inputs.pMonth.value='11';
run(`
  localDB.ready=true;sec.locked=false;save=()=>Promise.resolve(true);
  let notice='';toast=x=>{notice=x;};
  const e={id:'SYN',name:'測試員工',payType:'monthly',base:36000,hire:'2024-01-03',sched:defaultSched()};
  const ym='2026-11', empty={pending:0,needsProof:0,approved:0,unknown:0};
  state.employees=[e];const r=mrec(e.id,ym);
`);
(async()=>{
  assert.equal(run('setConfirm(e.id,true)'),false);
  for(const status of ['pending','approved','needsProof','unknown']){
    await run(`runLeaveCloseCheck(ym,async()=>({...empty,${status}:1}))`);
    assert.equal(run('setConfirm(e.id,true)'),false,status);
  }
  await run('runLeaveCloseCheck(ym,async()=>empty)');
  assert.equal(run('setConfirm(e.id,true)'),true);
  assert.equal(run('state.log.some(x=>x.action==="確認時核對正式假單")'),true);
  assert.equal(run('payrollReadyForOutput(false)'),true);
  run('const snap=JSON.stringify(r.snapshot)');
  await run('runLeaveCloseCheck(ym,async()=>({...empty,pending:1}))');
  assert.equal(run('payrollReadyForOutput(false)'),false);
  assert.equal(run('JSON.stringify(r.snapshot)===snap'),true);
  await run('runLeaveCloseCheck(ym,async()=>empty)');
  assert.equal(run('payrollReadyForOutput(false)'),true);
  assert.equal(run('leaveCloseBlock("2026-12").length>0'),true);
  await assert.rejects(run('runLeaveCloseCheck(ym,async()=>{throw Error("offline")})'),/offline/);
  assert.equal(run('payrollReadyForOutput(false)'),false);
  await assert.rejects(run('runLeaveCloseCheck(ym,async()=>{invalidateLeaveCloseCheck();return empty})'),/變更/);
  run('verifiedLeaveClose(ym,empty,Date.now()-LEAVE_CLOSE_WINDOW_MS)');
  assert.equal(run('payrollReadyForOutput(false)'),false);
  await assert.rejects(run('runLeaveCloseCheck(ym,async()=>({pending:0}))'),/不完整/);
  assert.equal(run('payrollReadyForOutput(false)'),false);

  const {readLeaveCloseCounts}=await import('../leave-public/portal.mjs');
  const dataset=Array.from({length:68},(_,i)=>({date:'2026-11-07',scope:'production',status:i===54?'approved':i===62?'pending':'manual'}));
  dataset.push({date:'2026-11-22',scope:'test',status:'pending'},{date:'2026-12-01',scope:'production',status:'pending'});
  let reads=0;
  const fake={
    where:(...a)=>['where',...a],orderBy:(...a)=>['sort',...a],
    limit:n=>['limit',n],startAfter:row=>['after',row.index],query:(_,...parts)=>parts,
    async getDocsFromServer(parts){
      reads++;let docs=dataset.map((d,index)=>({index,data:()=>d})).filter(row=>parts.every(([type,k,op,v])=>type!=='where'||(op==='=='?row.data()[k]===v:op==='>='?row.data()[k]>=v:row.data()[k]<=v)));
      const after=parts.find(x=>x[0]==='after');
      if(after)docs=docs.filter(row=>row.index>after[1]);
      return {docs:docs.slice(0,parts.find(x=>x[0]==='limit')[1])};
    }
  };
  assert.deepEqual(await readLeaveCloseCounts(fake,{},'2026-11'),{pending:1,needsProof:0,approved:1,unknown:0});
  assert.equal(reads,2);
  const online=fake.getDocsFromServer;
  fake.getDocsFromServer=async parts=>{if(parts.some(x=>x[0]==='after'))throw Error('lost connection');return online(parts);};
  await assert.rejects(readLeaveCloseCounts(fake,{},'2026-11'),/lost connection/);
  assert.deepEqual(await readLeaveCloseCounts(fake,{},'2026-12'),{pending:1,needsProof:0,approved:0,unknown:0});
  console.log('PASS: fail-closed confirmed outputs, scoped server query including later pages, and historical snapshot preservation.');
})().catch(e=>{console.error(e);process.exitCode=1;});
